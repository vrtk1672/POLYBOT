from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id
from app.utils.json_safety import json_safe


DEFAULT_MAX_PENDING_SECONDS = 600
DEFAULT_MAX_EXECUTION_ATTEMPTS = 2
DEFAULT_REACTIVATION_MIN_DELTA_SCORE = Decimal("1.0")
ACTIVE_INTENT_STATUSES = {"CREATED", "READY", "EXECUTING"}
EXPIRED_INTENT_STATUSES = {
    "EXPIRED",
    "EXPIRED_NO_EXECUTION",
    "CANCELLED_STALE_INTENT",
    "CANCELLED_REPLACED_BY_NEW_EVIDENCE",
    "CANCELLED_SESSION_RESET",
}
MEMORY_WAITING_STATUSES = {"REMEMBERED", "WAITING_FOR_NEW_EVIDENCE"}


class OpportunityMemoryService:
    """Paper-only opportunity memory, intent expiry, and reactivation ledger.

    This service does not authorize execution. It converts stale non-executed
    Paper intents into explicit lifecycle records, remembers their evidence
    fingerprint, and lets the normal Mesh reactivate only when evidence changes.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self.max_pending_seconds = _int_env("PAPER_INTENT_MAX_PENDING_SECONDS", DEFAULT_MAX_PENDING_SECONDS)
        self.max_execution_attempts = _int_env("PAPER_INTENT_MAX_EXECUTION_ATTEMPTS", DEFAULT_MAX_EXECUTION_ATTEMPTS)
        self.reactivation_min_delta_score = _decimal_env(
            "PAPER_OPPORTUNITY_REACTIVATION_MIN_DELTA_SCORE",
            DEFAULT_REACTIVATION_MIN_DELTA_SCORE,
        )
        self.memory_enabled = _bool_env("PAPER_OPPORTUNITY_MEMORY_ENABLED", True)
        self.reactivation_requires_new_evidence = _bool_env("PAPER_OPPORTUNITY_REACTIVATION_REQUIRES_NEW_EVIDENCE", True)

    def expire_stale_intents(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "expired_count": 0, "remembered_count": 0}
        with self._factory.connect() as conn, conn.transaction():
            return self.expire_stale_intents_for_connection(conn, limit=limit)

    def expire_stale_intents_for_connection(
        self,
        conn: Any,
        *,
        limit: int = 100,
        paper_session_id: str | None = None,
    ) -> dict[str, Any]:
        if not self.memory_enabled or not _table_exists(conn, "paper_intents"):
            return {"status": "DISABLED", "expired_count": 0, "remembered_count": 0, "items": []}
        if not _table_exists(conn, "opportunity_memory"):
            return {"status": "SCHEMA_MISSING", "expired_count": 0, "remembered_count": 0, "items": []}
        session_id = paper_session_id or active_paper_session_id(conn)
        rows = _stale_pending_intents(
            conn,
            session_id=session_id,
            max_pending_seconds=self.max_pending_seconds,
            max_execution_attempts=self.max_execution_attempts,
            limit=max(1, min(int(limit or 100), 500)),
        )
        expired: list[dict[str, Any]] = []
        for intent in rows:
            memory = self.remember_intent(
                conn,
                intent,
                status="WAITING_FOR_NEW_EVIDENCE",
                reason=_expiry_reason(intent),
            )
            _expire_intent(conn, intent, memory)
            expired.append(
                {
                    "paper_intent_id": intent.get("paper_intent_id"),
                    "market_id": intent.get("market_id"),
                    "side": intent.get("side"),
                    "age_seconds": _age_seconds(intent.get("created_at")),
                    "status": "EXPIRED_NO_EXECUTION",
                    "reason": _expiry_reason(intent),
                    "opportunity_memory_id": memory.get("opportunity_memory_id"),
                    "evidence_fingerprint": memory.get("evidence_fingerprint"),
                }
            )
        return {
            "status": "OK",
            "active_paper_session_id": session_id,
            "expired_count": len(expired),
            "remembered_count": len(expired),
            "max_pending_seconds": self.max_pending_seconds,
            "max_execution_attempts": self.max_execution_attempts,
            "items": expired,
        }

    def evaluate_runtime_decision(
        self,
        conn: Any,
        row: dict[str, Any],
        *,
        paper_session_id: str | None,
    ) -> dict[str, Any]:
        fingerprint_payload = fingerprint_payload_from_row(row)
        fingerprint = evidence_fingerprint(fingerprint_payload)
        key = opportunity_key(row)
        if not self.memory_enabled or not _table_exists(conn, "opportunity_memory"):
            return {
                "enabled": self.memory_enabled,
                "opportunity_key": key,
                "evidence_fingerprint": fingerprint,
                "same_evidence_waiting": False,
                "reactivation_available": False,
            }
        same = _memory_for_fingerprint(conn, paper_session_id, key, fingerprint)
        previous = _latest_memory_for_key(conn, paper_session_id, key, exclude_fingerprint=fingerprint)
        return {
            "enabled": True,
            "opportunity_key": key,
            "evidence_fingerprint": fingerprint,
            "same_evidence_waiting": same is not None,
            "same_evidence_memory_id": same.get("opportunity_memory_id") if same else None,
            "reactivation_available": previous is not None and same is None,
            "reactivated_from_memory_id": previous.get("opportunity_memory_id") if previous else None,
            "previous_evidence_fingerprint": previous.get("evidence_fingerprint") if previous else None,
            "requires_new_evidence": self.reactivation_requires_new_evidence,
            "status": "WAITING_FOR_NEW_EVIDENCE" if same else "NEW_OR_CHANGED_EVIDENCE",
        }

    def attach_intent_metadata(self, conn: Any, intent_row: dict[str, Any]) -> dict[str, Any]:
        if not self.memory_enabled or not _table_exists(conn, "paper_intents"):
            return intent_row
        payload = fingerprint_payload_from_intent(intent_row)
        fingerprint = evidence_fingerprint(payload)
        key = opportunity_key(intent_row)
        session_id = intent_row.get("paper_session_id") or active_paper_session_id(conn)
        previous = _latest_memory_for_key(conn, session_id, key, exclude_fingerprint=fingerprint) if _table_exists(conn, "opportunity_memory") else None
        reactivated_from = previous.get("opportunity_memory_id") if previous else None
        if previous:
            _record_reactivation_event(conn, intent_row, previous, fingerprint)
        columns = _columns(conn, "paper_intents")
        updates: list[str] = []
        params: dict[str, Any] = {"paper_intent_id": intent_row.get("paper_intent_id")}
        if "evidence_fingerprint" in columns:
            updates.append("evidence_fingerprint = %(evidence_fingerprint)s")
            params["evidence_fingerprint"] = fingerprint
        if "reactivated_from_memory_id" in columns:
            updates.append("reactivated_from_memory_id = %(reactivated_from_memory_id)s")
            params["reactivated_from_memory_id"] = reactivated_from
        if "updated_at" in columns:
            updates.append("updated_at = now()")
        if not updates:
            return intent_row
        row = conn.execute(
            f"""
            UPDATE paper_intents
            SET {", ".join(updates)}
            WHERE paper_intent_id = %(paper_intent_id)s
            RETURNING *
            """,
            params,
        ).fetchone()
        return dict(row) if row else intent_row

    def remember_intent(self, conn: Any, intent: dict[str, Any], *, status: str, reason: str) -> dict[str, Any]:
        payload = fingerprint_payload_from_intent(intent)
        fingerprint = evidence_fingerprint(payload)
        key = opportunity_key(intent)
        memory_id = memory_id_for(intent.get("paper_session_id"), key, fingerprint)
        evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
        source = evidence.get("source_evidence") if isinstance(evidence.get("source_evidence"), dict) else evidence
        row = conn.execute(
            """
            INSERT INTO opportunity_memory (
                opportunity_memory_id, paper_session_id, market_id, side,
                original_candidate_id, original_runtime_decision_id,
                original_paper_intent_id, latest_runtime_decision_id,
                latest_paper_intent_id, opportunity_key, evidence_fingerprint,
                status, last_seen_at, last_decision, last_blockers_json,
                last_score, last_defense_level, last_side_evidence_json,
                last_arbitration_json, last_exit_state, last_reason,
                created_at, updated_at
            )
            VALUES (
                %(opportunity_memory_id)s, %(paper_session_id)s, %(market_id)s, %(side)s,
                %(original_candidate_id)s, %(original_runtime_decision_id)s,
                %(original_paper_intent_id)s, %(latest_runtime_decision_id)s,
                %(latest_paper_intent_id)s, %(opportunity_key)s, %(evidence_fingerprint)s,
                %(status)s, now(), %(last_decision)s, %(last_blockers_json)s,
                %(last_score)s, %(last_defense_level)s, %(last_side_evidence_json)s,
                %(last_arbitration_json)s, %(last_exit_state)s, %(last_reason)s,
                now(), now()
            )
            ON CONFLICT (paper_session_id, opportunity_key, evidence_fingerprint) DO UPDATE SET
                latest_runtime_decision_id = COALESCE(EXCLUDED.latest_runtime_decision_id, opportunity_memory.latest_runtime_decision_id),
                latest_paper_intent_id = COALESCE(EXCLUDED.latest_paper_intent_id, opportunity_memory.latest_paper_intent_id),
                status = EXCLUDED.status,
                last_seen_at = now(),
                last_decision = EXCLUDED.last_decision,
                last_blockers_json = EXCLUDED.last_blockers_json,
                last_score = EXCLUDED.last_score,
                last_defense_level = EXCLUDED.last_defense_level,
                last_side_evidence_json = EXCLUDED.last_side_evidence_json,
                last_arbitration_json = EXCLUDED.last_arbitration_json,
                last_exit_state = EXCLUDED.last_exit_state,
                last_reason = EXCLUDED.last_reason,
                updated_at = now()
            RETURNING *
            """,
            {
                "opportunity_memory_id": memory_id,
                "paper_session_id": intent.get("paper_session_id"),
                "market_id": str(intent.get("market_id") or ""),
                "side": str(intent.get("side") or "").upper(),
                "original_candidate_id": intent.get("eligibility_id"),
                "original_runtime_decision_id": _runtime_decision_id(intent),
                "original_paper_intent_id": intent.get("paper_intent_id"),
                "latest_runtime_decision_id": _runtime_decision_id(intent),
                "latest_paper_intent_id": intent.get("paper_intent_id"),
                "opportunity_key": key,
                "evidence_fingerprint": fingerprint,
                "status": status,
                "last_decision": _source_value(source, "decision") or "INTENT_EXPIRED",
                "last_blockers_json": Jsonb(_source_blockers(intent, source)),
                "last_score": _decimal_or_none(_source_value(source, "opportunity_score") or _source_value(source, "eligibility_score")),
                "last_defense_level": _defense_level(source),
                "last_side_evidence_json": Jsonb(json_safe(_nested(source, "side_evidence") or _nested(source, "same_market_side_arbitration") or {})),
                "last_arbitration_json": Jsonb(json_safe(_nested(source, "same_market_arbitration") or _nested(source, "same_market_opposing_enter_arbitration") or {})),
                "last_exit_state": _source_value(source, "exit_state"),
                "last_reason": reason,
            },
        ).fetchone()
        return dict(row)

    def opportunity_memory(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        with self._factory.connect() as conn:
            return self.opportunity_memory_for_connection(conn, limit=limit)

    def opportunity_memory_for_connection(self, conn: Any, *, limit: int = 100, session_id: str | None = None) -> dict[str, Any]:
        if not _table_exists(conn, "opportunity_memory"):
            return {"status": "SCHEMA_MISSING", "items": [], "counts": {}}
        session_id = session_id or active_paper_session_id(conn)
        rows = _fetch_memory(conn, session_id=session_id, limit=limit)
        counts = _memory_counts(conn, session_id=session_id)
        return json_safe(
            {
                "status": "OK",
                "active_paper_session_id": session_id,
                "counts": counts,
                "items": rows,
                "policy": self.policy(),
                "safety": _safety(conn),
            }
        )

    def expired_intents(self, *, limit: int = 100) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        with self._factory.connect() as conn:
            return self.expired_intents_for_connection(conn, limit=limit)

    def expired_intents_for_connection(self, conn: Any, *, limit: int = 100, session_id: str | None = None) -> dict[str, Any]:
        if not _table_exists(conn, "paper_intents"):
            return {"status": "SCHEMA_MISSING", "items": [], "counts": {}}
        session_id = session_id or active_paper_session_id(conn)
        rows = _fetch_expired_intents(conn, session_id=session_id, limit=limit)
        return json_safe(
            {
                "status": "OK",
                "active_paper_session_id": session_id,
                "counts": _expired_counts(conn, session_id=session_id),
                "items": rows,
                "policy": self.policy(),
                "safety": _safety(conn),
            }
        )

    def policy(self) -> dict[str, Any]:
        return {
            "paper_intent_max_pending_seconds": self.max_pending_seconds,
            "paper_intent_max_execution_attempts": self.max_execution_attempts,
            "paper_opportunity_reactivation_min_delta_score": str(self.reactivation_min_delta_score),
            "paper_opportunity_reactivation_requires_new_evidence": self.reactivation_requires_new_evidence,
            "paper_opportunity_memory_enabled": self.memory_enabled,
        }


def fingerprint_payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    runtime_decision = evidence.get("paper_runtime_decision") if isinstance(evidence.get("paper_runtime_decision"), dict) else {}
    policy = evidence.get("paper_mode_policy") if isinstance(evidence.get("paper_mode_policy"), dict) else {}
    defense = evidence.get("paper_defense") if isinstance(evidence.get("paper_defense"), dict) else {}
    source_ids = _extract_source_ids({**evidence, **runtime_decision})
    return _canonical(
        {
            "market_id": row.get("market_id") or runtime_decision.get("market_id"),
            "condition_id": row.get("condition_id") or runtime_decision.get("condition_id"),
            "side": str(row.get("side") or runtime_decision.get("side") or "").upper(),
            "token_id": row.get("token_id") or runtime_decision.get("token_id"),
            "orderbook_snapshot_id": row.get("orderbook_snapshot_id") or evidence.get("orderbook_snapshot_id"),
            "best_bid": _round_decimal(evidence.get("orderbook_best_bid") or runtime_decision.get("orderbook_best_bid")),
            "best_ask": _round_decimal(evidence.get("orderbook_best_ask") or runtime_decision.get("orderbook_best_ask")),
            "mid_price": _round_decimal(evidence.get("orderbook_mid_price") or evidence.get("orderbook_mid")),
            "score": _round_decimal(row.get("opportunity_score") or runtime_decision.get("opportunity_score") or row.get("eligibility_score")),
            "decision": row.get("decision") or runtime_decision.get("decision"),
            "paper_enter_allowed": row.get("paper_enter_allowed") if "paper_enter_allowed" in row else policy.get("paper_enter_allowed"),
            "edge_state": row.get("edge_state") or runtime_decision.get("edge_state"),
            "thesis_state": row.get("thesis_state") or runtime_decision.get("thesis_state"),
            "exit_state": row.get("exit_state") or runtime_decision.get("exit_state"),
            "risk_state": row.get("risk_state") or runtime_decision.get("risk_state"),
            "capital_state": row.get("capital_state") or runtime_decision.get("capital_state"),
            "blockers": _sorted_list(row.get("blockers_json") or row.get("eligibility_blockers") or runtime_decision.get("blockers_json") or policy.get("blockers")),
            "warnings": _sorted_list(row.get("warnings_json") or runtime_decision.get("warnings_json") or policy.get("warnings")),
            "defense": {
                "level": _nested(defense, "defense_level") or _nested(policy, "paper_defense", "defense_level"),
                "adjusted_threshold": _round_decimal(_nested(defense, "profile", "adjusted_threshold") or policy.get("adjusted_threshold")),
                "exit_plan_type": defense.get("exit_plan_type") if isinstance(defense, dict) else None,
            },
            "side_evidence": _canonical(_nested(evidence, "side_evidence") or _nested(evidence, "same_market_side_arbitration") or {}),
            "arbitration": _canonical(_nested(evidence, "same_market_arbitration") or _nested(evidence, "same_market_opposing_enter_arbitration") or {}),
            "source_ids": source_ids,
        }
    )


def fingerprint_payload_from_intent(intent: dict[str, Any]) -> dict[str, Any]:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    source = evidence.get("source_evidence") if isinstance(evidence.get("source_evidence"), dict) else evidence
    row_like = {
        **source,
        "market_id": intent.get("market_id") or source.get("market_id"),
        "side": intent.get("side") or source.get("side"),
        "token_id": source.get("token_id"),
        "orderbook_snapshot_id": intent.get("orderbook_snapshot_id") or source.get("orderbook_snapshot_id"),
        "opportunity_score": _source_value(source, "opportunity_score") or evidence.get("eligibility_score"),
        "eligibility_blockers": intent.get("blockers") or source.get("blockers_json"),
        "evidence": source,
    }
    return fingerprint_payload_from_row(row_like)


def evidence_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(json_safe(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def opportunity_key(row: dict[str, Any]) -> str:
    return f"{row.get('market_id')}|{str(row.get('side') or '').upper()}"


def memory_id_for(session_id: Any, key: str, fingerprint: str) -> str:
    raw = f"{session_id}|{key}|{fingerprint}"
    return f"opportunity_memory_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _stale_pending_intents(
    conn: Any,
    *,
    session_id: str | None,
    max_pending_seconds: int,
    max_execution_attempts: int,
    limit: int,
) -> list[dict[str, Any]]:
    columns = _columns(conn, "paper_intents")
    session_clause = "AND (%s::text IS NULL OR pi.paper_session_id=%s::text)" if "paper_session_id" in columns else "AND %s::text IS NULL AND %s::text IS NULL"
    attempts_expr = "COALESCE(pi.execution_attempt_count,0)" if "execution_attempt_count" in columns else "0"
    rows = conn.execute(
        f"""
        SELECT pi.*
        FROM paper_intents pi
        WHERE pi.intent_status IN ('CREATED','READY','EXECUTING')
          AND pi.intent_type='PAPER_ENTRY_INTENT'
          AND COALESCE(pi.paper_only, true) = true
          AND COALESCE(pi.live, false) = false
          AND COALESCE(pi.is_dry_run_generated, false) = false
          {session_clause}
          AND (
              pi.created_at <= now() - (%s::int * interval '1 second')
              OR ({attempts_expr} >= %s::int AND pi.created_at <= now() - interval '60 seconds')
          )
          AND NOT EXISTS (
              SELECT 1 FROM paper_orders po
              WHERE po.payload_json->>'source_intent_id' = pi.paper_intent_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM paper_fills pf
              WHERE pf.source_intent_id = pi.paper_intent_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM paper_positions pp
              WHERE pp.payload_json->>'source_intent_id' = pi.paper_intent_id
          )
        ORDER BY pi.created_at ASC, pi.id ASC
        LIMIT %s
        """,
        (session_id, session_id, max_pending_seconds, max_execution_attempts, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _expire_intent(conn: Any, intent: dict[str, Any], memory: dict[str, Any]) -> None:
    columns = _columns(conn, "paper_intents")
    assignments = [
        "intent_status = 'EXPIRED_NO_EXECUTION'",
        "updated_at = now()",
    ]
    if "expired_at" in columns:
        assignments.append("expired_at = COALESCE(expired_at, now())")
    if "closed_at" in columns:
        assignments.append("closed_at = COALESCE(closed_at, now())")
    if "consumed_at" in columns:
        assignments.append("consumed_at = COALESCE(consumed_at, now())")
    if "intent_lifecycle_reason" in columns:
        assignments.append("intent_lifecycle_reason = %(reason)s")
    if "opportunity_memory_id" in columns:
        assignments.append("opportunity_memory_id = %(opportunity_memory_id)s")
    if "evidence_fingerprint" in columns:
        assignments.append("evidence_fingerprint = %(evidence_fingerprint)s")
    conn.execute(
        f"""
        UPDATE paper_intents
        SET {", ".join(assignments)}
        WHERE paper_intent_id = %(paper_intent_id)s
          AND intent_status IN ('CREATED','READY','EXECUTING')
        """,
        {
            "paper_intent_id": intent.get("paper_intent_id"),
            "reason": _expiry_reason(intent),
            "opportunity_memory_id": memory.get("opportunity_memory_id"),
            "evidence_fingerprint": memory.get("evidence_fingerprint"),
        },
    )


def _expiry_reason(intent: dict[str, Any]) -> str:
    reason = str(intent.get("execution_block_reason") or "").strip()
    if reason:
        return f"EXPIRED_NO_EXECUTION:{reason}"
    return "EXPIRED_NO_EXECUTION:PENDING_OVER_MAX_PENDING_SECONDS"


def _memory_for_fingerprint(conn: Any, session_id: str | None, key: str, fingerprint: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM opportunity_memory
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
          AND opportunity_key=%s
          AND evidence_fingerprint=%s
          AND status IN ('REMEMBERED','WAITING_FOR_NEW_EVIDENCE')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (session_id, session_id, key, fingerprint),
    ).fetchone()
    return dict(row) if row else None


def _latest_memory_for_key(
    conn: Any,
    session_id: str | None,
    key: str,
    *,
    exclude_fingerprint: str | None = None,
) -> dict[str, Any] | None:
    extra = "AND evidence_fingerprint<>%s" if exclude_fingerprint else ""
    params: list[Any] = [session_id, session_id, key]
    if exclude_fingerprint:
        params.append(exclude_fingerprint)
    row = conn.execute(
        f"""
        SELECT *
        FROM opportunity_memory
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
          AND opportunity_key=%s
          AND status IN ('REMEMBERED','WAITING_FOR_NEW_EVIDENCE')
          {extra}
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return dict(row) if row else None


def _record_reactivation_event(conn: Any, intent: dict[str, Any], memory: dict[str, Any], fingerprint: str) -> None:
    if not _table_exists(conn, "opportunity_reactivation_events"):
        return
    raw_event_key = f"{memory.get('opportunity_memory_id')}|{intent.get('paper_intent_id')}|{fingerprint}"
    event_id = f"opportunity_reactivation_{hashlib.sha256(raw_event_key.encode('utf-8')).hexdigest()[:24]}"
    conn.execute(
        """
        INSERT INTO opportunity_reactivation_events (
            reactivation_event_id, opportunity_memory_id, paper_session_id,
            market_id, side, previous_evidence_fingerprint, new_evidence_fingerprint,
            runtime_decision_id, paper_intent_id, reason, evidence_delta_json, created_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'EVIDENCE_FINGERPRINT_CHANGED', %s, now())
        ON CONFLICT (reactivation_event_id) DO NOTHING
        """,
        (
            event_id,
            memory.get("opportunity_memory_id"),
            intent.get("paper_session_id"),
            intent.get("market_id"),
            intent.get("side"),
            memory.get("evidence_fingerprint"),
            fingerprint,
            _runtime_decision_id(intent),
            intent.get("paper_intent_id"),
            Jsonb(json_safe({"previous_status": memory.get("status"), "source": "PaperIntentGateService"})),
        ),
    )
    conn.execute(
        """
        UPDATE opportunity_memory
        SET status='REACTIVATED',
            reactivation_count=reactivation_count+1,
            last_seen_at=now(),
            updated_at=now()
        WHERE opportunity_memory_id=%s
        """,
        (memory.get("opportunity_memory_id"),),
    )


def _fetch_memory(conn: Any, *, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM opportunity_memory
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
        ORDER BY updated_at DESC, id DESC
        LIMIT %s
        """,
        (session_id, session_id, max(1, min(int(limit or 100), 500))),
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_expired_intents(conn: Any, *, session_id: str | None, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM paper_intents
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
          AND intent_status IN (
              'EXPIRED','EXPIRED_NO_EXECUTION','CANCELLED_STALE_INTENT',
              'CANCELLED_REPLACED_BY_NEW_EVIDENCE','CANCELLED_SESSION_RESET'
          )
        ORDER BY COALESCE(expired_at, cancelled_at, updated_at, created_at) DESC NULLS LAST, id DESC
        LIMIT %s
        """,
        (session_id, session_id, max(1, min(int(limit or 100), 500))),
    ).fetchall()
    return [dict(row) for row in rows]


def _memory_counts(conn: Any, *, session_id: str | None) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS count, COALESCE(SUM(reactivation_count),0) AS reactivations
        FROM opportunity_memory
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
        GROUP BY status
        """,
        (session_id, session_id),
    ).fetchall()
    counts = {str(row["status"]): int(row["count"] or 0) for row in rows}
    counts["reactivated_opportunities"] = sum(int(row["reactivations"] or 0) for row in rows)
    counts["remembered_total"] = sum(value for key, value in counts.items() if key != "reactivated_opportunities")
    return counts


def _expired_counts(conn: Any, *, session_id: str | None) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT intent_status, COUNT(*) AS count
        FROM paper_intents
        WHERE (%s::text IS NULL OR paper_session_id=%s::text)
          AND intent_status IN (
              'EXPIRED','EXPIRED_NO_EXECUTION','CANCELLED_STALE_INTENT',
              'CANCELLED_REPLACED_BY_NEW_EVIDENCE','CANCELLED_SESSION_RESET'
          )
        GROUP BY intent_status
        """,
        (session_id, session_id),
    ).fetchall()
    return {str(row["intent_status"]): int(row["count"] or 0) for row in rows}


def _safety(conn: Any) -> dict[str, Any]:
    return {
        "paper_only": True,
        "live_orders": _count_table(conn, "live_orders"),
        "shadow_orders": _count_table(conn, "shadow_orders"),
        "real_orders": _real_order_count(conn, "orders") + _real_order_count(conn, "orders_v2"),
    }


def _recordable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical(value: Any) -> Any:
    value = json_safe(value)
    if isinstance(value, dict):
        return {
            str(key): _canonical(val)
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            if val not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return _recordable(value)


def _extract_source_ids(source: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "source_event_id",
        "source_event_ids",
        "linked_event_ids",
        "news_id",
        "news_ids",
        "trigger_id",
        "trigger_ids",
        "multi_trigger_id",
        "proactive_seed_id",
        "proactive_candidate_seed_id",
        "orderbook_snapshot_id",
        "side_evidence_id",
        "arbitration_id",
    }
    return _canonical({key: source.get(key) for key in keys if key in source})


def _source_blockers(intent: dict[str, Any], source: dict[str, Any]) -> list[str]:
    return _sorted_list(
        intent.get("blockers")
        or source.get("blockers_json")
        or _nested(source, "paper_mode_policy", "blockers")
        or _nested(source, "paper_defense", "strict_blockers")
    )


def _runtime_decision_id(intent: dict[str, Any]) -> str | None:
    evidence = intent.get("evidence") if isinstance(intent.get("evidence"), dict) else {}
    source = evidence.get("source_evidence") if isinstance(evidence.get("source_evidence"), dict) else evidence
    return (
        evidence.get("paper_runtime_decision_id")
        or source.get("paper_runtime_decision_id")
        or source.get("decision_id")
        or _nested(source, "paper_runtime_decision", "decision_id")
    )


def _source_value(source: dict[str, Any], key: str) -> Any:
    if key in source:
        return source.get(key)
    runtime_decision = source.get("paper_runtime_decision") if isinstance(source.get("paper_runtime_decision"), dict) else {}
    return runtime_decision.get(key)


def _defense_level(source: dict[str, Any]) -> int | None:
    value = _nested(source, "paper_defense", "defense_level") or _nested(source, "paper_mode_policy", "paper_defense", "defense_level")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sorted_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = [value]
    return sorted({str(item).upper() for item in values if str(item or "").strip()})


def _round_decimal(value: Any) -> str | None:
    decimal = _decimal_or_none(value)
    if decimal is None:
        return None
    return str(decimal.quantize(Decimal("0.0001")))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


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


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _columns(conn: Any, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
          AND table_name=%s
        """,
        (table,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def _real_order_count(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    columns = _columns(conn, table)
    if "execution_mode" not in columns:
        return _count_table(conn, table)
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM {table}
        WHERE UPPER(COALESCE(execution_mode, '')) NOT IN
          ('PAPER','PAPER_SIM','PAPER_SIM_EXIT','SHADOW','SHADOW_PLAN','CONTRACT_ONLY')
        """
    ).fetchone()
    return int(row["count"] or 0)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _decimal_env(name: str, default: Decimal) -> Decimal:
    try:
        return Decimal(str(os.getenv(name, str(default))))
    except Exception:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
