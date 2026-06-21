from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id
from app.utils.json_safety import json_safe


INTENT_STUCK_SECONDS = 600
INTEGRITY_BLOCKERS = {
    "MISSING_MARKET_ID",
    "MISSING_TOKEN_ID",
    "INVALID_SIDE",
    "TOKEN_SIDE_NOT_VERIFIED",
    "MISSING_FRESH_ORDERBOOK",
    "STALE_ORDERBOOK",
    "ORDERBOOK_NOT_FRESH",
    "MISSING_TRUSTED_ORDERBOOK",
    "MISSING_EXECUTABLE_PRICE",
    "MISSING_QUANTITY",
    "CAPITAL_HARD_BLOCKED",
    "RISK_HARD_BLOCKED",
    "RISK_BLOCKED",
    "LIVE_INTENT_BLOCKED",
    "NOT_PAPER_ONLY",
    "EXECUTION_ALLOWED_UNEXPECTED",
}
STRATEGIC_BLOCKERS = {
    "EXISTING_HARD_BLOCKERS_PRESENT",
    "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD",
    "DECISION_BAND_NOT_PAPER_OBSERVATION",
    "EDGE_NOT_SUPPORTED",
    "THESIS_NOT_SUPPORTED",
    "EXIT_NOT_READY",
    "OBSERVATION_POLICY_NOT_ALLOWED",
}
DUPLICATE_BLOCKERS = {
    "DUPLICATE_ACTIVE_PAPER_INTENT",
    "DUPLICATE_OPEN_PAPER_EXPOSURE",
    "SAME_MARKET_DUPLICATE_DECISION",
    "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW",
    "ALREADY_INTENT_EXISTS_FOR_ELIGIBILITY",
    "OPPORTUNITY_WAITING_FOR_NEW_EVIDENCE",
}
ARBITRATION_BLOCKERS = {
    "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION",
    "SAME_MARKET_OPPOSING_ENTER_CONFLICT",
    "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION",
    "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
    "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION",
}


class OpportunityMeshCoordinator:
    """Computed Full Mesh opportunity pool and lifecycle router.

    This service does not create orders, fills, positions, or fake candidates. It
    reconstructs current opportunity state from existing runtime truth and gives
    duplicate/blocked/intent states a lifecycle route so they do not masquerade
    as terminal system failures.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def opportunity_mesh(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        limit = max(1, min(int(limit or 100), 500))
        with self._factory.connect() as conn:
            return self.opportunity_mesh_for_connection(conn, limit=limit)

    def opportunity_mesh_for_connection(self, conn: Any, *, limit: int = 100, session_id: str | None = None) -> dict[str, Any]:
        limit = max(1, min(int(limit or 100), 500))
        tables = _tables(conn)
        session_id = session_id or active_paper_session_id(conn)
        decisions = _current_decisions(conn, tables, limit=limit)
        intents = _session_intents(conn, tables, session_id=session_id, limit=limit)
        intent_by_decision = _intent_by_runtime_decision(intents)
        active_intent_by_market_side = {
            (str(item.get("market_id")), str(item.get("side")).upper()): item
            for item in intents
            if str(item.get("intent_status") or "").upper() in {"CREATED", "READY", "EXECUTING"}
        }
        items: list[dict[str, Any]] = []
        for decision in decisions:
            key = (str(decision.get("market_id")), str(decision.get("side")).upper())
            intent = intent_by_decision.get(str(decision.get("decision_id") or "")) or active_intent_by_market_side.get(key)
            items.append(_state_from_decision(conn, tables, decision, intent, session_id))
        represented_intents = {str((item.get("paper_lifecycle") or {}).get("paper_intent_id")) for item in items if (item.get("paper_lifecycle") or {}).get("paper_intent_id")}
        for intent in intents:
            if str(intent.get("paper_intent_id")) in represented_intents:
                continue
            items.append(_state_from_intent(conn, tables, intent, session_id))
        summary = _summary(items)
        return json_safe(
            {
                "status": "OK",
                "active_paper_session_id": session_id,
                "generated_at": datetime.now(UTC),
                "summary": summary,
                "items": items[:limit],
                "candidate_consumption": _candidate_consumption(items),
                "intent_queue": _intent_queue(conn, tables, session_id=session_id, limit=limit),
                "safety": _safety(conn, tables),
            }
        )

    def intent_queue(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        limit = max(1, min(int(limit or 100), 500))
        with self._factory.connect() as conn:
            tables = _tables(conn)
            session_id = active_paper_session_id(conn)
            items = _intent_queue(conn, tables, session_id=session_id, limit=limit)
            counts = Counter(str(item.get("execution_status") or "UNKNOWN") for item in items)
            return json_safe(
                {
                    "status": "OK",
                    "active_paper_session_id": session_id,
                    "counts": dict(counts),
                    "stuck_count": sum(1 for item in items if item.get("stuck")),
                    "items": items,
                    "safety": _safety(conn, tables),
                }
            )

    def candidate_consumption(self, *, limit: int = 100) -> dict[str, Any]:
        payload = self.opportunity_mesh(limit=limit)
        return {
            "status": payload.get("status"),
            "active_paper_session_id": payload.get("active_paper_session_id"),
            "candidate_consumption": payload.get("candidate_consumption") or {},
            "summary": payload.get("summary") or {},
            "items": [
                {
                    "market_id": item.get("market_id"),
                    "side": item.get("side"),
                    "runtime_decision_id": item.get("runtime_decision_id"),
                    "lifecycle_state": item.get("lifecycle_state"),
                    "consumption_policy": item.get("consumption_policy"),
                    "next_action": item.get("next_action"),
                    "status_reason": item.get("status_reason"),
                }
                for item in payload.get("items", [])
            ],
            "safety": payload.get("safety") or {},
        }


def _state_from_decision(conn: Any, tables: dict[str, set[str]], decision: dict[str, Any], intent: dict[str, Any] | None, session_id: str | None) -> dict[str, Any]:
    blockers = _list(decision.get("blockers_json"))
    warnings = _list(decision.get("warnings_json"))
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), dict) else {}
    defense = evidence.get("paper_defense") if isinstance(evidence.get("paper_defense"), dict) else {}
    lifecycle_state = "WATCHING"
    next_action = "MONITOR"
    owning_organ = "PaperRuntimeDecisionService"
    consumption_policy = "CONSUME_SKIP_BLOCKED_CONTINUE"
    status_reason = "Candidate is not enterable yet."

    if intent:
        intent_state = _intent_execution_state(conn, tables, intent, session_id)
        lifecycle_state = "HAS_ACTIVE_INTENT" if intent_state["lifecycle_state"] == "INTENT_PENDING_EXECUTION" else intent_state["lifecycle_state"]
        next_action = "CHECK_INTENT_EXECUTION" if lifecycle_state == "HAS_ACTIVE_INTENT" else intent_state["next_action"]
        owning_organ = "PaperExecutionService"
        consumption_policy = "CONSUME_ROUTE_TO_EXECUTION"
        status_reason = intent_state["status_reason"]
        execution_status = intent_state["lifecycle_state"]
    else:
        execution_status = None
    if not intent and _has_any(blockers, ARBITRATION_BLOCKERS):
        lifecycle_state = "ARBITRATED_DEMOTED" if "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION" in blockers or "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION" in blockers else "RETRY_LATER"
        next_action = "WAIT_FOR_SIDE_EVIDENCE" if lifecycle_state != "ARBITRATED_DEMOTED" else "NONE"
        owning_organ = "SameMarketSideArbitrator"
        consumption_policy = "CONSUME_SKIP_BLOCKED_CONTINUE"
        status_reason = _first_matching(blockers, ARBITRATION_BLOCKERS) or "ARBITRATION_STATE"
    elif not intent and _has_any(blockers, DUPLICATE_BLOCKERS):
        lifecycle_state = "SKIPPED_DUPLICATE"
        next_action = "CHECK_INTENT_EXECUTION"
        owning_organ = "OpportunityMeshCoordinator"
        consumption_policy = "CONSUME_SKIP_DUPLICATE_CONTINUE"
        status_reason = _first_matching(blockers, DUPLICATE_BLOCKERS) or "DUPLICATE"
    elif not intent and _has_any(blockers, INTEGRITY_BLOCKERS):
        lifecycle_state = "BLOCKED_INTEGRITY"
        next_action = "NONE"
        owning_organ = _owner_for_blockers(blockers)
        consumption_policy = "CONSUME_SKIP_BLOCKED_CONTINUE"
        status_reason = _first_matching(blockers, INTEGRITY_BLOCKERS) or "INTEGRITY_BLOCK"
    elif not intent and str(decision.get("decision") or "").upper() == "ENTER" and bool(decision.get("paper_enter_allowed")):
        ignored = _list(defense.get("ignored_blockers"))
        softened = _list(defense.get("softened_blockers"))
        lifecycle_state = "ALLOWED_FOR_LEARNING" if ignored or softened else "READY_FOR_INTENT"
        next_action = "CREATE_PAPER_INTENT"
        owning_organ = "PaperIntentGateService"
        consumption_policy = "CONSUME_CREATE_INTENT"
        status_reason = "Defense-adjusted ENTER is ready for PaperIntentGate."
    elif not intent and _has_any(blockers, STRATEGIC_BLOCKERS):
        lifecycle_state = "BLOCKED_STRATEGIC"
        next_action = "RETRY_LATER"
        owning_organ = _owner_for_blockers(blockers)
        consumption_policy = "CONSUME_SKIP_BLOCKED_CONTINUE"
        status_reason = _first_matching(blockers, STRATEGIC_BLOCKERS) or "STRATEGIC_BLOCK"

    return {
        "paper_session_id": session_id,
        "market_id": decision.get("market_id"),
        "side": decision.get("side"),
        "candidate_id": decision.get("proactive_candidate_seed_id") or decision.get("source_review_id"),
        "runtime_decision_id": decision.get("decision_id"),
        "paper_intent_id": (intent or {}).get("paper_intent_id"),
        "score": _float(decision.get("opportunity_score")),
        "decision": decision.get("decision"),
        "lifecycle_state": lifecycle_state,
        "current_status": lifecycle_state,
        "next_action": next_action,
        "owning_organ": owning_organ,
        "status_reason": status_reason,
        "consumption_policy": consumption_policy,
        "blockers": blockers,
        "warnings": warnings,
        "softened_blockers": _list(defense.get("softened_blockers")) if isinstance(defense, dict) else [],
        "ignored_blockers": _list(defense.get("ignored_blockers")) if isinstance(defense, dict) else [],
        "defense_level": _nested(defense, "defense_level"),
        "adjusted_threshold": _nested(defense, "profile", "adjusted_threshold"),
        "side_evidence_summary": _nested(evidence, "same_market_side_arbitration") or _nested(evidence, "side_evidence"),
        "arbitration_summary": _nested(evidence, "same_market_arbitration") or _nested(evidence, "same_market_opposing_enter_arbitration"),
        "paper_lifecycle": _paper_lifecycle(conn, tables, (intent or {}).get("paper_intent_id"), session_id),
        "execution_status": execution_status,
        "updated_at": decision.get("updated_at"),
    }


def _state_from_intent(conn: Any, tables: dict[str, set[str]], intent: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    intent_state = _intent_execution_state(conn, tables, intent, session_id)
    return {
        "paper_session_id": session_id,
        "market_id": intent.get("market_id"),
        "side": intent.get("side"),
        "candidate_id": intent.get("eligibility_id"),
        "runtime_decision_id": _nested(intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}, "paper_runtime_decision_id"),
        "paper_intent_id": intent.get("paper_intent_id"),
        "score": None,
        "decision": "INTENT_ONLY",
        "lifecycle_state": intent_state["lifecycle_state"],
        "current_status": intent_state["lifecycle_state"],
        "next_action": intent_state["next_action"],
        "owning_organ": "PaperExecutionService",
        "status_reason": intent_state["status_reason"],
        "consumption_policy": "CONSUME_ROUTE_TO_EXECUTION",
        "blockers": _list(intent.get("blockers")),
        "warnings": [],
        "softened_blockers": [],
        "ignored_blockers": [],
        "defense_level": None,
        "adjusted_threshold": None,
        "side_evidence_summary": None,
        "arbitration_summary": None,
        "paper_lifecycle": _paper_lifecycle(conn, tables, intent.get("paper_intent_id"), session_id),
        "execution_status": intent_state["lifecycle_state"],
        "updated_at": intent.get("updated_at"),
    }


def _intent_execution_state(conn: Any, tables: dict[str, set[str]], intent: dict[str, Any], session_id: str | None) -> dict[str, str]:
    lifecycle = _paper_lifecycle(conn, tables, intent.get("paper_intent_id"), session_id)
    status = str(intent.get("intent_status") or "").upper()
    if status in {"EXPIRED", "EXPIRED_NO_EXECUTION"}:
        return {
            "lifecycle_state": "INTENT_EXPIRED",
            "next_action": "WAIT_FOR_NEW_EVIDENCE",
            "status_reason": str(intent.get("intent_lifecycle_reason") or "EXPIRED_NO_EXECUTION"),
        }
    if status in {"CANCELLED", "CANCELLED_STALE_INTENT", "CANCELLED_REPLACED_BY_NEW_EVIDENCE", "CANCELLED_SESSION_RESET"}:
        return {
            "lifecycle_state": "INTENT_CANCELLED",
            "next_action": "WAIT_FOR_NEW_EVIDENCE",
            "status_reason": str(intent.get("intent_lifecycle_reason") or status),
        }
    if lifecycle.get("position_close_id") or lifecycle.get("position_closed") or str(intent.get("intent_status") or "").upper() == "CLOSED":
        return {"lifecycle_state": "POSITION_CLOSED", "next_action": "NONE", "status_reason": "Paper position has been closed for this intent."}
    if lifecycle.get("position_id"):
        return {"lifecycle_state": "POSITION_OPEN", "next_action": "ROUTE_TO_EXIT", "status_reason": "Paper position exists for this intent."}
    if lifecycle.get("fill_id"):
        return {"lifecycle_state": "FILL_CREATED", "next_action": "OPEN_OR_VERIFY_POSITION", "status_reason": "Paper fill exists for this intent."}
    if lifecycle.get("order_id"):
        return {"lifecycle_state": "ORDER_CREATED", "next_action": "VERIFY_FILL", "status_reason": "Paper order exists for this intent."}
    reason = str(intent.get("execution_block_reason") or "").upper()
    age = _age_seconds(intent.get("created_at"))
    if reason or age >= INTENT_STUCK_SECONDS:
        detail = reason or "PENDING_OVER_STUCK_THRESHOLD"
        next_action = "REFRESH_ORDERBOOK_OR_EXPIRE_INTENT" if "ORDERBOOK" in detail or "STALE" in detail else "DIAGNOSE_EXECUTION"
        return {"lifecycle_state": "INTENT_STUCK", "next_action": next_action, "status_reason": detail}
    return {"lifecycle_state": "INTENT_PENDING_EXECUTION", "next_action": "EXECUTE_PAPER_INTENT", "status_reason": "Intent is current-session CREATED and awaiting execution."}


def _intent_queue(conn: Any, tables: dict[str, set[str]], *, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    out = []
    for intent in _session_intents(conn, tables, session_id=session_id, limit=limit):
        state = _intent_execution_state(conn, tables, intent, session_id)
        lifecycle = _paper_lifecycle(conn, tables, intent.get("paper_intent_id"), session_id)
        out.append(
            {
                "paper_session_id": session_id,
                "paper_intent_id": intent.get("paper_intent_id"),
                "eligibility_id": intent.get("eligibility_id"),
                "market_id": intent.get("market_id"),
                "side": intent.get("side"),
                "intent_status": intent.get("intent_status"),
                "age_seconds": _age_seconds(intent.get("created_at")),
                "execution_status": state["lifecycle_state"],
                "next_action": state["next_action"],
                "execution_block_reason": intent.get("execution_block_reason"),
                "last_execution_attempt_at": intent.get("last_execution_attempt_at"),
                "execution_attempt_count": intent.get("execution_attempt_count"),
                "expired_at": intent.get("expired_at"),
                "cancelled_at": intent.get("cancelled_at"),
                "intent_lifecycle_reason": intent.get("intent_lifecycle_reason"),
                "opportunity_memory_id": intent.get("opportunity_memory_id"),
                "evidence_fingerprint": intent.get("evidence_fingerprint"),
                "reactivated_from_memory_id": intent.get("reactivated_from_memory_id"),
                "stuck": state["lifecycle_state"] == "INTENT_STUCK",
                "expired": state["lifecycle_state"] == "INTENT_EXPIRED",
                "cancelled": state["lifecycle_state"] == "INTENT_CANCELLED",
                "order_id": lifecycle.get("order_id"),
                "fill_id": lifecycle.get("fill_id"),
                "position_id": lifecycle.get("position_id"),
                "execution_price_source": lifecycle.get("execution_price_source"),
                "trusted_orderbook_used": lifecycle.get("trusted_orderbook_used"),
                "fallback_source": lifecycle.get("fallback_source"),
                "fallback_reason": lifecycle.get("fallback_reason"),
                "price_confidence": lifecycle.get("price_confidence"),
                "created_at": intent.get("created_at"),
                "updated_at": intent.get("updated_at"),
            }
        )
    return out


def _current_decisions(conn: Any, tables: dict[str, set[str]], *, limit: int) -> list[dict[str, Any]]:
    if "paper_runtime_decisions" not in tables:
        return []
    current = "is_current_batch IS TRUE" if "is_current_batch" in tables["paper_runtime_decisions"] else "true"
    rows = conn.execute(
        f"""
        SELECT *
        FROM paper_runtime_decisions
        WHERE {current}
        ORDER BY
          CASE decision WHEN 'ENTER' THEN 0 WHEN 'WATCH' THEN 1 ELSE 2 END,
          opportunity_score DESC NULLS LAST,
          updated_at DESC NULLS LAST,
          id DESC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def _session_intents(conn: Any, tables: dict[str, set[str]], *, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    if "paper_intents" not in tables:
        return []
    session_clause = "AND (%s::text IS NULL OR paper_session_id=%s::text)" if "paper_session_id" in tables["paper_intents"] else "AND %s::text IS NULL AND %s::text IS NULL"
    rows = conn.execute(
        f"""
        SELECT *
        FROM paper_intents
        WHERE intent_type='PAPER_ENTRY_INTENT'
          {session_clause}
        ORDER BY
          CASE intent_status WHEN 'CREATED' THEN 0 WHEN 'READY' THEN 1 WHEN 'EXECUTING' THEN 2 ELSE 3 END,
          created_at DESC NULLS LAST,
          id DESC
        LIMIT %s
        """,
        (session_id, session_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _intent_by_runtime_decision(intents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for intent in intents:
        evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
        decision_id = evidence.get("paper_runtime_decision_id")
        if decision_id:
            out[str(decision_id)] = intent
    return out


def _paper_lifecycle(conn: Any, tables: dict[str, set[str]], intent_id: Any, session_id: str | None) -> dict[str, Any]:
    if not intent_id:
        return {"paper_intent_id": None, "order_id": None, "fill_id": None, "position_id": None, "position_close_id": None}
    order = _first_by_intent(conn, tables, "paper_orders", "payload_json->>'source_intent_id'", intent_id, session_id)
    fill = _first_by_intent(conn, tables, "paper_fills", "source_intent_id", intent_id, session_id)
    position = _first_by_intent(conn, tables, "paper_positions", "payload_json->>'source_intent_id'", intent_id, session_id)
    close = None
    if position and "paper_position_closes" in tables:
        close = conn.execute(
            """
            SELECT *
            FROM paper_position_closes
            WHERE position_id=%s
              AND (%s::text IS NULL OR paper_session_id=%s::text)
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (position.get("id"), session_id, session_id),
        ).fetchone()
    return {
        "paper_intent_id": intent_id,
        "order_id": str(order.get("id")) if order else None,
        "fill_id": fill.get("paper_fill_id") if fill else None,
        "position_id": str(position.get("id")) if position else None,
        "execution_price_source": _json_value(fill, "metadata_json", "execution_price_source") or _json_value(order, "payload_json", "execution_price_source"),
        "trusted_orderbook_used": _json_value(fill, "metadata_json", "trusted_orderbook_used") or _json_value(order, "payload_json", "trusted_orderbook_used"),
        "fallback_source": _json_value(fill, "metadata_json", "fallback_source") or _json_value(order, "payload_json", "fallback_source"),
        "fallback_reason": _json_value(fill, "metadata_json", "fallback_reason") or _json_value(order, "payload_json", "fallback_reason"),
        "price_confidence": _json_value(fill, "metadata_json", "price_confidence") or _json_value(order, "payload_json", "price_confidence"),
        "position_status": position.get("current_status") if position else None,
        "position_closed": bool(position and (position.get("closed_at") or str(position.get("current_status") or "").upper() in {"CLOSED", "RESET_CLOSED", "RESET_ARCHIVED"})),
        "position_close_id": (close.get("close_id") or close.get("position_close_id") or close.get("id")) if close else None,
    }


def _json_value(row: dict[str, Any] | None, column: str, key: str) -> Any:
    if not row:
        return None
    payload = row.get(column)
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _first_by_intent(conn: Any, tables: dict[str, set[str]], table: str, expr: str, intent_id: Any, session_id: str | None) -> dict[str, Any] | None:
    if table not in tables:
        return None
    session_clause = "AND (%s::text IS NULL OR paper_session_id=%s::text)" if "paper_session_id" in tables[table] else "AND %s::text IS NULL AND %s::text IS NULL"
    timestamp_col = _timestamp_column(tables, table)
    row = conn.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE {expr}=%s
          {session_clause}
        ORDER BY {timestamp_col} DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (intent_id, session_id, session_id),
    ).fetchone()
    return dict(row) if row else None


def _timestamp_column(tables: dict[str, set[str]], table: str) -> str:
    columns = tables.get(table) or set()
    for candidate in ("created_at", "filled_at", "opened_at", "updated_at"):
        if candidate in columns:
            return candidate
    return "id"


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    states = Counter(str(item.get("lifecycle_state") or "UNKNOWN") for item in items)
    actions = Counter(str(item.get("next_action") or "UNKNOWN") for item in items)
    policies = Counter(str(item.get("consumption_policy") or "UNKNOWN") for item in items)
    intent_pending = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_PENDING_EXECUTION" or item.get("execution_status") == "INTENT_PENDING_EXECUTION")
    intent_stuck = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_STUCK" or item.get("execution_status") == "INTENT_STUCK")
    intent_expired = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_EXPIRED" or item.get("execution_status") == "INTENT_EXPIRED")
    intent_cancelled = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_CANCELLED" or item.get("execution_status") == "INTENT_CANCELLED")
    return {
        "active_pool_size": len(items),
        "lifecycle_counts": dict(states),
        "next_action_counts": dict(actions),
        "consumption_policy_counts": dict(policies),
        "ready_for_intent": states.get("READY_FOR_INTENT", 0) + states.get("ALLOWED_FOR_LEARNING", 0),
        "already_has_active_intent": states.get("HAS_ACTIVE_INTENT", 0),
        "intent_pending_execution": intent_pending,
        "intent_stuck": intent_stuck,
        "intent_expired": intent_expired,
        "intent_cancelled": intent_cancelled,
        "blocked_integrity": states.get("BLOCKED_INTEGRITY", 0),
        "blocked_strategic": states.get("BLOCKED_STRATEGIC", 0),
        "softened_by_defense": states.get("ALLOWED_FOR_LEARNING", 0),
        "arbitrated_selected": states.get("ARBITRATED_SELECTED", 0),
        "arbitrated_demoted": states.get("ARBITRATED_DEMOTED", 0),
        "skipped_duplicate": states.get("SKIPPED_DUPLICATE", 0),
        "routed_to_execution": policies.get("CONSUME_ROUTE_TO_EXECUTION", 0),
        "routed_to_exit": actions.get("ROUTE_TO_EXIT", 0),
        "system_errors": 0,
    }


def _candidate_consumption(items: list[dict[str, Any]]) -> dict[str, Any]:
    policies = Counter(str(item.get("consumption_policy") or "UNKNOWN") for item in items)
    states = Counter(str(item.get("lifecycle_state") or "UNKNOWN") for item in items)
    intent_stuck = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_STUCK" or item.get("execution_status") == "INTENT_STUCK")
    intent_expired = sum(1 for item in items if item.get("lifecycle_state") == "INTENT_EXPIRED" or item.get("execution_status") == "INTENT_EXPIRED")
    return {
        "candidates_consumed": len(items),
        "created_intents": policies.get("CONSUME_CREATE_INTENT", 0),
        "skipped_duplicate": policies.get("CONSUME_SKIP_DUPLICATE_CONTINUE", 0),
        "skipped_blocked": policies.get("CONSUME_SKIP_BLOCKED_CONTINUE", 0),
        "routed_to_execution": policies.get("CONSUME_ROUTE_TO_EXECUTION", 0),
        "routed_to_exit": states.get("POSITION_OPEN", 0),
        "retry_later": sum(1 for item in items if item.get("next_action") in {"RETRY_LATER", "WAIT_FOR_SIDE_EVIDENCE"}),
        "expired": states.get("EXPIRED", 0) + intent_expired,
        "intent_stuck": intent_stuck,
        "system_errors": 0,
    }


def _safety(conn: Any, tables: dict[str, set[str]]) -> dict[str, int | bool]:
    return {
        "paper_only": True,
        "live_orders": _count(conn, tables, "live_orders"),
        "shadow_orders": _count(conn, tables, "shadow_orders"),
        "real_orders": _real_order_count(conn, tables, "orders") + _real_order_count(conn, tables, "orders_v2"),
    }


def _real_order_count(conn: Any, tables: dict[str, set[str]], table: str) -> int:
    if table not in tables:
        return 0
    if "execution_mode" not in tables[table]:
        return _count(conn, tables, table)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table}
        WHERE UPPER(COALESCE(execution_mode, '')) NOT IN
          ('PAPER','PAPER_SIM','PAPER_SIM_EXIT','SHADOW','SHADOW_PLAN','CONTRACT_ONLY')
        """
    ).fetchone()
    return int(row["count"] or 0)


def _tables(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema=current_schema()").fetchall()
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return out


def _has_any(values: list[str], candidates: set[str]) -> bool:
    normalized = {str(item).upper() for item in values}
    return bool(normalized.intersection(candidates))


def _first_matching(values: list[str], candidates: set[str]) -> str | None:
    normalized = [str(item).upper() for item in values]
    return next((item for item in normalized if item in candidates), None)


def _owner_for_blockers(blockers: list[str]) -> str:
    first = str(blockers[0]).upper() if blockers else "UNKNOWN"
    if "ORDERBOOK" in first:
        return "Orderbook Mesh"
    if "EXIT" in first:
        return "Exit Mesh"
    if "RISK" in first:
        return "Risk Mesh"
    if "CAPITAL" in first:
        return "Capital Mesh"
    if "THESIS" in first:
        return "Trade Thesis Mesh"
    if "EDGE" in first:
        return "Source-Backed Edge Mesh"
    return "OpportunityMeshCoordinator"


def _age_seconds(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0
    if not isinstance(value, datetime):
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - value.astimezone(UTC)).total_seconds()))


def _count(conn: Any, tables: dict[str, set[str]], table: str) -> int:
    if table not in tables:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, Decimal):
        return float(current)
    return current
