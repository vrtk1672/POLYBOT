from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_session import active_paper_session_id
from app.utils.json_safety import json_safe

PAPER_THRESHOLD = Decimal("60")

BLOCKER_MAP: dict[str, dict[str, Any]] = {
    "EXISTING_HARD_BLOCKERS_PRESENT": {
        "organ": "ObservationPolicy / PaperRuntimeDecision",
        "severity": "HARD",
        "meaning": "The upstream policy review still has hard blockers.",
        "actionable": "Clear the underlying hard blockers in the policy review.",
    },
    "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD": {
        "organ": "PaperRuntimeDecision",
        "severity": "SOFT",
        "meaning": "Opportunity score is below the PAPER decision threshold.",
        "actionable": "Opportunity score must increase to >= 60 through stronger edge, thesis, exit, liquidity, or source evidence.",
    },
    "DECISION_BAND_NOT_PAPER_OBSERVATION": {
        "organ": "OpportunityScore / ObservationPolicy",
        "severity": "HARD",
        "meaning": "Candidate did not classify into PAPER_OBSERVATION.",
        "actionable": "Opportunity decision band must become PAPER_OBSERVATION.",
    },
    "EDGE_NOT_SUPPORTED": {
        "organ": "Edge Mesh",
        "severity": "HARD",
        "meaning": "Source-backed edge is not supported.",
        "actionable": "Evidence must support a real market edge.",
    },
    "THESIS_NOT_SUPPORTED": {
        "organ": "Trade Thesis Mesh",
        "severity": "HARD",
        "meaning": "Trade thesis is missing or not supported.",
        "actionable": "Trade thesis must become THESIS_SUPPORTED or an explicitly allowed PAPER learning thesis.",
    },
    "EXIT_NOT_READY": {
        "organ": "Exit Mesh",
        "severity": "HARD",
        "meaning": "Exit/time-stop/invalidation is not ready.",
        "actionable": "Exit plan must define target, invalidation, and time stop.",
    },
    "OBSERVATION_POLICY_NOT_ALLOWED": {
        "organ": "PaperObservationPolicy",
        "severity": "HARD",
        "meaning": "Observation policy did not allow this candidate.",
        "actionable": "Policy state must become OBSERVATION_POLICY_ELIGIBLE or enterable policy must explicitly allow it.",
    },
    "DUPLICATE_OPEN_PAPER_EXPOSURE": {
        "organ": "PaperRuntimeDecision / SameMarketSideGuard",
        "severity": "HARD",
        "meaning": "A same market/side paper exposure is already open.",
        "actionable": "Existing same market/side exposure must close or explicit duplicate exposure policy must be introduced.",
    },
    "SAME_MARKET_DUPLICATE_DECISION": {
        "organ": "PaperRuntimeDecision",
        "severity": "HARD",
        "meaning": "Another same market/side decision already exists in this batch.",
        "actionable": "Use the best grouped decision for that market/side; duplicates stay suppressed.",
    },
    "DUPLICATE_ACTIVE_PAPER_INTENT": {
        "organ": "PaperRuntimeDecision / PaperIntentGate",
        "severity": "HARD",
        "meaning": "A fresh active paper intent already exists for this market/side.",
        "actionable": "Consume or expire the existing intent before another is created.",
    },
    "SAME_MARKET_OPPOSING_ENTER_CONFLICT": {
        "organ": "PaperRuntimeDecision",
        "severity": "HARD",
        "meaning": "Both YES and NO reached ENTER for the same market in one PAPER batch without a clear winner.",
        "actionable": "One side must have stronger source-backed evidence, or both sides remain blocked/watch.",
    },
    "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION": {
        "organ": "PaperRuntimeDecision",
        "severity": "HARD",
        "meaning": "The opposite side had stronger source-backed evidence in same-market arbitration.",
        "actionable": "This side must become the stronger same-market side before PAPER entry.",
    },
    "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION": {
        "organ": "SameMarketSideArbitrator",
        "severity": "HARD",
        "meaning": "The opposite side won defense-aware same-market arbitration for this PAPER batch.",
        "actionable": "This side must show stronger side-specific evidence, better execution quality, or a better arbitration score.",
    },
    "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED": {
        "organ": "SameMarketSideArbitrator",
        "severity": "HARD",
        "meaning": "YES/NO evidence was too close for the active Paper Defense Level.",
        "actionable": "One side must separate on thesis, edge, exit, orderbook, liquidity, or defense-adjusted arbitration score.",
    },
    "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION": {
        "organ": "SameMarketSideArbitrator / SystemIntegrity",
        "severity": "INTEGRITY",
        "meaning": "Same-market arbitration could not choose a side because integrity blockers remained.",
        "actionable": "Clear market/token/session/accounting/execution integrity blockers before arbitration can select a side.",
    },
    "ORDERBOOK_NOT_FRESH": {
        "organ": "Orderbook Mesh",
        "severity": "HARD",
        "meaning": "Orderbook state is not fresh.",
        "actionable": "Refresh and verify the exact token/side orderbook.",
    },
}


class DecisionAutopsyService:
    """Read-only forensic view over Full Mesh PAPER decisions and paper lifecycle."""

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def list_autopsies(
        self,
        *,
        limit: int = 25,
        paper_session_id: str | None = None,
        market_id: str | None = None,
        side: str | None = None,
        action: str | None = None,
        include_historical: bool = False,
    ) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            active_session = paper_session_id or active_paper_session_id(conn)
            rows = _runtime_decisions(
                conn,
                tables,
                limit=limit,
                market_id=market_id,
                side=side,
                action=action,
                include_historical=include_historical,
            )
            items = [_build_autopsy(conn, tables, row, active_session) for row in rows]
            return json_safe(
                {
                    "status": "OK",
                    "active_paper_session_id": active_session,
                    "items": items,
                    "count": len(items),
                    "tables": _audit_tables(tables),
                    "services": _service_map(),
                }
            )

    def top_blockers(self, *, limit: int = 20) -> dict[str, Any]:
        payload = self.list_autopsies(limit=250, include_historical=False)
        counts: Counter[str] = Counter()
        samples: dict[str, list[dict[str, Any]]] = {}
        missing_by_code: dict[str, Counter[str]] = {}
        actionable_by_code: dict[str, Counter[str]] = {}
        observed_by_code: dict[str, dict[str, Any]] = {}
        current_session_codes: set[str] = set()
        latest_cycle_codes: set[str] = set()
        for item in payload.get("items", []):
            for code in item.get("blocker_codes", []):
                code = str(code)
                counts[code] += 1
                if item.get("paper_session_id"):
                    current_session_codes.add(code)
                latest_cycle_codes.add(code)
                missing_by_code.setdefault(code, Counter()).update(str(value) for value in item.get("missing_requirements", []) if value)
                actionable_by_code.setdefault(code, Counter()).update(str(value) for value in item.get("what_would_make_actionable", []) if value)
                observed_by_code.setdefault(code, item.get("observed_values") or {})
                samples.setdefault(code, [])
                if len(samples[code]) < 3:
                    samples[code].append(
                        {
                            "market_id": item.get("market_id"),
                            "side": item.get("side"),
                            "action": item.get("action"),
                            "score": item.get("score"),
                            "runtime_decision_id": item.get("runtime_decision_id"),
                            "decision_band": item.get("decision_band"),
                        }
                    )
        rows = []
        for code, count in counts.most_common(limit):
            meta = _blocker_meta(code)
            primary_missing = _counter_top(missing_by_code.get(code))
            primary_action = _actionable_for_blocker(code, _counter_top(actionable_by_code.get(code)), meta)
            observed = observed_by_code.get(code) or {}
            required_value = _required_value_for_blocker(code, primary_missing)
            rows.append(
                {
                    "blocker_code": code,
                    "count": count,
                    "blocking_organ": meta["organ"],
                    "blocking_gate": meta["organ"],
                    "severity": meta["severity"],
                    "blocker_type": meta["severity"],
                    "meaning": meta["meaning"],
                    "plain_english_meaning": meta["meaning"],
                    "required_value_or_missing_requirement": required_value,
                    "what_would_make_actionable": primary_action,
                    "expected": code not in {"ENTER_WITHOUT_INTENT", "UNEXPECTED_EXECUTION_DELTA"},
                    "expected_vs_suspicious": "SUSPICIOUS" if code in {"ENTER_WITHOUT_INTENT", "UNEXPECTED_EXECUTION_DELTA"} else "EXPECTED",
                    "bug_suspect": code in {"ENTER_WITHOUT_INTENT", "UNEXPECTED_EXECUTION_DELTA"},
                    "affects_current_active_paper_session": code in current_session_codes,
                    "appeared_in_latest_runtime_cycle": code in latest_cycle_codes,
                    "trend": "UNKNOWN",
                    "observed_values": observed,
                    "samples": samples.get(code, []),
                    "example": (samples.get(code) or [{}])[0],
                }
            )
        return json_safe(
            {
                "status": "OK",
                "limit": limit,
                "active_paper_session_id": payload.get("active_paper_session_id"),
                "top_blockers": rows,
            }
        )

    def enter_autopsy(self, *, limit: int = 50) -> dict[str, Any]:
        payload = self.list_autopsies(limit=limit, action="ENTER", include_historical=True)
        return json_safe({"status": "OK", "items": payload.get("items", []), "count": payload.get("count", 0)})

    def closest_actionable(self, *, limit: int = 20) -> dict[str, Any]:
        payload = self.list_autopsies(limit=200, include_historical=False)
        items = sorted(
            payload.get("items", []),
            key=lambda item: (
                len(item.get("missing_requirements", [])),
                -float(item.get("score") or 0),
                0 if item.get("action") == "ENTER" else 1,
            ),
        )
        return json_safe({"status": "OK", "items": items[:limit]})

    def supervisor_autopsy(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE"}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            services = _latest_service_health(conn, tables)
            cycles = _latest_runtime_cycles(conn, tables)
            failed_runs = _latest_failed_runs(conn, tables)
            degraded = [
                item
                for item in services
                if str(item.get("status") or item.get("health_status") or "").upper() in {"ERROR", "DEGRADED", "STALE"}
                or item.get("last_error")
                or (isinstance(item.get("details_json"), dict) and item.get("details_json", {}).get("last_error"))
            ]
            reasons = [_service_reason(item) for item in degraded]
            reasons.extend(f"{item['table']}:{item.get('status')}:{item.get('error_message') or item.get('latest_error')}" for item in failed_runs)
            return json_safe(
                {
                    "status": "OK",
                    "supervisor_state": "DEGRADED" if reasons else "RUNNING_OR_IDLE",
                    "degraded_reasons": reasons,
                    "affected_organs": [str(item.get("service_name") or item.get("component") or item.get("table")) for item in degraded],
                    "latest_runtime_cycles": cycles,
                    "latest_failed_runs": failed_runs,
                    "blocks_paper_entries": False,
                    "explanation": "DEGRADED is diagnostic unless StateGovernor or PaperIntentGate reports execution blockers.",
                }
            )

    def paper_delta_autopsy(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DATABASE_UNAVAILABLE", "items": []}
        with self._factory.connect() as conn:
            tables = _tables(conn)
            mode = _current_runtime_mode(conn, tables)
            rows = _latest_delta_runs(conn, tables)
            items = []
            for row in rows:
                deltas = {
                    "paper_intents_delta": max(0, _int(row.get("paper_intents_after")) - _int(row.get("paper_intents_before"))),
                    "paper_orders_delta": _int(row.get("paper_orders_delta")),
                    "paper_fills_delta": _int(row.get("paper_fills_delta")),
                    "paper_positions_delta": _int(row.get("paper_positions_delta")),
                }
                total = sum(deltas.values())
                classification = "NO_CHANGE"
                severity = "INFO"
                if total > 0 and mode == "PAPER":
                    classification = "EXPECTED_ACTIVITY"
                elif total > 0 and mode in {"DATA_ONLY", "OFF", "KILL", "COOLDOWN"}:
                    classification = "SUSPICIOUS_ACTIVITY"
                    severity = "ERROR"
                items.append({**row, "deltas": deltas, "classification": classification, "severity": severity, "runtime_mode": mode})
            return json_safe(
                {
                    "status": "OK",
                    "runtime_mode": mode,
                    "items": items,
                    "latest_errors_should_include_expected_paper_activity": False,
                    "summary": Counter(str(item["classification"]) for item in items),
                }
            )


def _build_autopsy(conn: Any, tables: dict[str, set[str]], row: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    decision_id = str(row.get("decision_id") or "")
    blockers = _list(row.get("blockers_json"))
    warnings = _list(row.get("warnings_json"))
    required = _list(row.get("required_to_pass_json"))
    policy = _policy_review(conn, tables, row)
    no_trade = _no_trade(conn, tables, row, session_id)
    lifecycle = _paper_lifecycle(conn, tables, decision_id, session_id)
    action = str(row.get("decision") or "UNKNOWN").upper()
    missing = _missing_requirements(row, blockers, policy)
    suspicion = []
    stopped_at = "RUNTIME_DECISION"
    final_status = "WATCH" if action == "WATCH" else "BLOCKED" if blockers else "ENTER_READY"
    if lifecycle.get("intent_id"):
        stopped_at = "PAPER_EXECUTION_ADAPTER"
        final_status = "PAPER_INTENT_CREATED"
    if lifecycle.get("position_id"):
        stopped_at = "PAPER_POSITION"
        final_status = "POSITION_OPENED"
    if lifecycle.get("position_close_id"):
        stopped_at = "PAPER_POSITION_CLOSE"
        final_status = "POSITION_CLOSED"
    if action == "ENTER" and not lifecycle.get("intent_id"):
        skip_reason = _intent_skip_reason(blockers, no_trade)
        if skip_reason:
            final_status = "EXPECTED_DUPLICATE_BLOCK"
        else:
            suspicion.append("ENTER_WITHOUT_INTENT")
            final_status = "BUG_SUSPECT_ENTER_WITHOUT_INTENT"
            stopped_at = "PAPER_INTENT_GATE"
    why_not = _why_not(row, blockers, missing)
    return {
        "autopsy_id": f"autopsy_{decision_id}",
        "created_at": datetime.now(UTC).isoformat(),
        "paper_session_id": session_id,
        "market_id": row.get("market_id"),
        "side": row.get("side"),
        "candidate_id": row.get("proactive_candidate_seed_id") or row.get("source_review_id"),
        "runtime_decision_id": decision_id,
        "action": action,
        "score": _float(row.get("opportunity_score")),
        "thresholds": {"paper_threshold": float(PAPER_THRESHOLD), "observation_threshold": float(PAPER_THRESHOLD)},
        "decision_band": (policy or {}).get("decision_band"),
        "final_status": final_status,
        "lifecycle_stage_reached": stopped_at,
        "lifecycle_stopped_at": stopped_at,
        "blocking_organ": _blocking_organ(blockers, action, lifecycle),
        "blocker_codes": blockers,
        "warnings": warnings,
        "hard_blockers": [code for code in blockers if _blocker_meta(code)["severity"] == "HARD"],
        "soft_blockers": [code for code in blockers if _blocker_meta(code)["severity"] != "HARD"],
        "missing_requirements": missing,
        "observed_values": _observed_values(row, policy),
        "required_values": {"opportunity_score_min": float(PAPER_THRESHOLD)},
        "why_not": why_not,
        "what_would_make_actionable": _what_would_make_actionable(blockers, missing),
        "suspicion_flags": suspicion,
        "paper_lifecycle": lifecycle,
        "intent_gate_evaluation": {
            "selected_for_intent": action == "ENTER",
            "intent_created": bool(lifecycle.get("intent_id")),
            "intent_skip_reason": _intent_skip_reason(blockers, no_trade),
            "duplicate_scope": _duplicate_scope(blockers, no_trade),
            "processed_scope": _processed_scope(no_trade),
            "session_match": _session_match(session_id, lifecycle, no_trade),
            "bug_suspect": bool(suspicion),
        },
        "policy_review": policy,
        "no_trade_record": no_trade,
        "is_expected_block": not suspicion,
        "is_bug_suspect": bool(suspicion),
    }


def _runtime_decisions(conn: Any, tables: dict[str, set[str]], *, limit: int, market_id: str | None, side: str | None, action: str | None, include_historical: bool) -> list[dict[str, Any]]:
    if "paper_runtime_decisions" not in tables:
        return []
    where = []
    params: list[Any] = []
    if not include_historical and "is_current_batch" in tables["paper_runtime_decisions"]:
        where.append("is_current_batch IS TRUE")
    if market_id:
        where.append("market_id=%s")
        params.append(market_id)
    if side:
        where.append("side=%s")
        params.append(side.upper())
    if action:
        where.append("decision=%s")
        params.append(action.upper())
    predicate = " AND ".join(where) if where else "true"
    rows = conn.execute(
        f"""
        SELECT *
        FROM paper_runtime_decisions
        WHERE {predicate}
        ORDER BY
            CASE decision WHEN 'ENTER' THEN 0 WHEN 'WATCH' THEN 1 ELSE 2 END,
            opportunity_score DESC NULLS LAST,
            updated_at DESC,
            id DESC
        LIMIT %s
        """,
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def _policy_review(conn: Any, tables: dict[str, set[str]], decision: dict[str, Any]) -> dict[str, Any] | None:
    if "paper_observation_policy_reviews" not in tables:
        return None
    review_id = decision.get("source_review_id")
    row = None
    if review_id:
        row = conn.execute(
            "SELECT * FROM paper_observation_policy_reviews WHERE paper_observation_policy_review_id=%s LIMIT 1",
            (review_id,),
        ).fetchone()
    if not row and decision.get("market_id") and decision.get("side"):
        row = conn.execute(
            """
            SELECT *
            FROM paper_observation_policy_reviews
            WHERE market_id=%s AND side=%s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC, id DESC
            LIMIT 1
            """,
            (decision.get("market_id"), decision.get("side")),
        ).fetchone()
    return json_safe(dict(row)) if row else None


def _no_trade(conn: Any, tables: dict[str, set[str]], decision: dict[str, Any], session_id: str | None) -> dict[str, Any] | None:
    if "no_trade_log" not in tables:
        return None
    session_filter = ""
    params: list[Any] = [decision.get("market_id"), decision.get("side")]
    if session_id:
        session_filter = "AND evidence->>'paper_session_id' = %s"
        params.append(session_id)
    row = conn.execute(
        f"""
        SELECT *
        FROM no_trade_log
        WHERE market_id=%s
          AND COALESCE(side,'')=COALESCE(%s,'')
          {session_filter}
        ORDER BY updated_at DESC NULLS LAST, created_at DESC, id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return json_safe(dict(row)) if row else None


def _paper_lifecycle(conn: Any, tables: dict[str, set[str]], decision_id: str, session_id: str | None) -> dict[str, Any]:
    intent = None
    if "paper_intents" in tables:
        intent = conn.execute(
            """
            SELECT *
            FROM paper_intents
            WHERE evidence->>'paper_runtime_decision_id'=%s
              AND (%s::text IS NULL OR paper_session_id=%s::text)
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (decision_id, session_id, session_id),
        ).fetchone()
    intent_id = intent["paper_intent_id"] if intent else None
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
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (position["id"], session_id, session_id),
        ).fetchone()
    return {
        "intent_id": intent_id,
        "order_id": str(order["id"]) if order else None,
        "fill_id": fill["paper_fill_id"] if fill else None,
        "position_id": str(position["id"]) if position else None,
        "position_close_id": close["close_id"] if close else None,
        "intent_status": intent["intent_status"] if intent else None,
        "position_status": position["current_status"] if position else None,
    }


def _first_by_intent(conn: Any, tables: dict[str, set[str]], table: str, expr: str, intent_id: Any, session_id: str | None) -> dict[str, Any] | None:
    if not intent_id or table not in tables:
        return None
    order_clause = _order_clause(tables.get(table, set()))
    row = conn.execute(
        f"""
        SELECT *
        FROM {table}
        WHERE {expr}=%s
          AND (%s::text IS NULL OR paper_session_id=%s::text)
        ORDER BY {order_clause}
        LIMIT 1
        """,
        (intent_id, session_id, session_id),
    ).fetchone()
    return dict(row) if row else None


def _order_clause(cols: set[str]) -> str:
    if "created_at" in cols and "updated_at" in cols:
        return "created_at DESC NULLS LAST, updated_at DESC NULLS LAST, id DESC"
    if "created_at" in cols:
        return "created_at DESC NULLS LAST, id DESC"
    if "updated_at" in cols:
        return "updated_at DESC NULLS LAST, id DESC"
    return "id DESC"


def _intent_skip_reason(blockers: list[str], no_trade: dict[str, Any] | None) -> str | None:
    no_trade_blockers = _list((no_trade or {}).get("blockers"))
    evidence = (no_trade or {}).get("evidence") if isinstance((no_trade or {}).get("evidence"), dict) else {}
    bridge_outcome = str(evidence.get("bridge_outcome") or "").upper()
    combined = {str(item).upper() for item in [*blockers, *no_trade_blockers] if str(item or "").strip()}
    for code in (
        "DUPLICATE_OPEN_PAPER_EXPOSURE",
        "DUPLICATE_ACTIVE_PAPER_INTENT",
        "SAME_MARKET_DUPLICATE_DECISION",
        "SAME_MARKET_OPPOSING_ENTER_CONFLICT",
        "SAME_MARKET_OPPOSING_SIDE_LOST_ARBITRATION",
        "OPPOSING_SIDE_DEMOTED_BY_ARBITRATION",
        "SAME_MARKET_OPPOSING_SIDE_UNRESOLVED",
        "INTEGRITY_BLOCKER_PREVENTED_ARBITRATION",
        "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW",
        "DECISION_EXPIRED",
        "ORDERBOOK_NOT_FRESH",
        "MISSING_FRESH_ORDERBOOK",
        "STALE_ORDERBOOK",
        "SESSION_MISMATCH",
        "PAPER_ADAPTER_DISABLED",
        "PAPER_SIMULATION_OFF_NO_INTENT_CREATED",
        "SYSTEM_POWER_OFF",
        "RUNTIME_STOPPED",
        "RISK_OR_EXIT_BLOCKED",
        "EXIT_NOT_READY",
        "RISK_NOT_APPROVED",
        "PAPER_RUNTIME_DECISION_DENIED",
    ):
        if code in combined:
            return code
    if bridge_outcome and bridge_outcome not in {"PAPER_INTENT_CREATED", "RESOLVED"}:
        return bridge_outcome
    return None


def _duplicate_scope(blockers: list[str], no_trade: dict[str, Any] | None) -> str:
    reason = _intent_skip_reason(blockers, no_trade)
    if reason in {"DUPLICATE_OPEN_PAPER_EXPOSURE", "DUPLICATE_ACTIVE_PAPER_INTENT", "SAME_MARKET_DUPLICATE_EXPOSURE_REVIEW"}:
        evidence = (no_trade or {}).get("evidence") if isinstance((no_trade or {}).get("evidence"), dict) else {}
        return str(evidence.get("duplicate_scope") or "CURRENT_SESSION").upper()
    return "NONE"


def _processed_scope(no_trade: dict[str, Any] | None) -> str:
    evidence = (no_trade or {}).get("evidence") if isinstance((no_trade or {}).get("evidence"), dict) else {}
    return str(evidence.get("processed_scope") or "NONE").upper()


def _session_match(session_id: str | None, lifecycle: dict[str, Any], no_trade: dict[str, Any] | None) -> bool:
    if lifecycle.get("intent_id"):
        return True
    evidence = (no_trade or {}).get("evidence") if isinstance((no_trade or {}).get("evidence"), dict) else {}
    seen = evidence.get("paper_session_id")
    return not session_id or not seen or str(seen) == str(session_id)


def _latest_service_health(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    if "service_health" not in tables:
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM service_health ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 50").fetchall()]


def _service_reason(item: dict[str, Any]) -> str:
    details = item.get("details_json") if isinstance(item.get("details_json"), dict) else {}
    latest = item.get("last_error") or details.get("last_error") or details.get("error") or ""
    return f"{item.get('service_name') or item.get('component')}: {item.get('status') or item.get('health_status')} {latest}".strip()


def _latest_runtime_cycles(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    if "runtime_cycles_v2" not in tables:
        return []
    return [dict(row) for row in conn.execute("SELECT * FROM runtime_cycles_v2 ORDER BY started_at DESC NULLS LAST, id DESC LIMIT 10").fetchall()]


def _latest_failed_runs(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    out = []
    for table in ("paper_runtime_decision_runs", "paper_intent_runs", "paper_execution_runs", "paper_exit_loop_runs", "candidate_eligibility_recovery_runs"):
        if table not in tables:
            continue
        row = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row and (str(row.get("status") or "").upper() in {"ERROR", "DEGRADED", "FAILED"} or row.get("error_message") or row.get("latest_error")):
            out.append({"table": table, **dict(row)})
    return out


def _latest_delta_runs(conn: Any, tables: dict[str, set[str]]) -> list[dict[str, Any]]:
    rows = []
    for table in ("candidate_eligibility_recovery_runs", "fresh_seed_paper_path_runs", "side_evidence_recovery_runs", "post_side_risk_exit_recovery_runs", "paper_execution_runs", "paper_exit_loop_runs"):
        if table not in tables:
            continue
        cols = tables[table]
        if not any(col in cols for col in ("paper_orders_delta", "paper_fills_delta", "paper_positions_delta", "paper_intents_after")):
            continue
        row = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row:
            rows.append({"table": table, **dict(row)})
    return rows


def _current_runtime_mode(conn: Any, tables: dict[str, set[str]]) -> str:
    if "system_state" in tables:
        row = conn.execute("SELECT * FROM system_state WHERE state_status='ACTIVE' ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row:
            return str(row.get("current_mode") or "UNKNOWN").upper()
    if "runtime_state" in tables:
        row = conn.execute("SELECT * FROM runtime_state ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row:
            return str(row.get("current_mode") or row.get("runtime_mode") or "UNKNOWN").upper()
    if "runtime_states" in tables:
        row = conn.execute("SELECT * FROM runtime_states ORDER BY updated_at DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        if row:
            return str(row.get("current_mode") or row.get("runtime_mode") or "UNKNOWN").upper()
    return "UNKNOWN"


def _missing_requirements(row: dict[str, Any], blockers: list[str], policy: dict[str, Any] | None) -> list[str]:
    missing = set(_list(row.get("required_to_pass_json")))
    if "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD" in blockers:
        missing.add("opportunity_score_min_60")
    if "THESIS_NOT_SUPPORTED" in blockers or str(row.get("thesis_state") or "").upper().startswith("THESIS_WATCH"):
        missing.add("supported_trade_thesis")
    if "EXIT_NOT_READY" in blockers:
        missing.add("exit_plan")
    if "EDGE_NOT_SUPPORTED" in blockers:
        missing.add("source_backed_edge")
    if "DECISION_BAND_NOT_PAPER_OBSERVATION" in blockers:
        missing.add("paper_observation_decision_band")
    if policy:
        missing.update(str(item) for item in _list(policy.get("required_to_pass_json")))
    return sorted(missing)


def _observed_values(row: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "opportunity_score": _float(row.get("opportunity_score")),
        "paper_threshold": float(PAPER_THRESHOLD),
        "edge_state": row.get("edge_state"),
        "thesis_state": row.get("thesis_state"),
        "exit_state": row.get("exit_state"),
        "risk_state": row.get("risk_state"),
        "capital_state": row.get("capital_state"),
        "policy_state": (policy or {}).get("observation_policy_state"),
    }


def _why_not(row: dict[str, Any], blockers: list[str], missing: list[str]) -> list[str]:
    reasons = []
    score = _decimal(row.get("opportunity_score"))
    if "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD" in blockers:
        reasons.append(f"Opportunity score {score} is below threshold {PAPER_THRESHOLD}.")
    for code in blockers:
        meta = _blocker_meta(code)
        if meta["meaning"] not in reasons:
            reasons.append(meta["meaning"])
    for item in missing:
        reasons.append(f"Missing requirement: {item}.")
    return reasons


def _what_would_make_actionable(blockers: list[str], missing: list[str]) -> list[str]:
    actions = []
    for code in blockers:
        actions.append(_blocker_meta(code)["actionable"])
    for item in missing:
        actions.append(f"Satisfy requirement: {item}.")
    return sorted(set(actions))


def _blocking_organ(blockers: list[str], action: str, lifecycle: dict[str, Any]) -> str:
    if lifecycle.get("position_id"):
        return "PaperExecutionAdapter"
    if action == "ENTER" and not lifecycle.get("intent_id"):
        return "PaperIntentGate"
    if blockers:
        return _blocker_meta(blockers[0])["organ"]
    return "FullMeshCoordinator"


def _blocker_meta(code: str) -> dict[str, Any]:
    return BLOCKER_MAP.get(str(code), {"organ": "UNMAPPED", "severity": "HARD", "meaning": f"Blocker {code} is present but has no owner mapping yet.", "actionable": f"Map and clear blocker {code}."})


def _counter_top(counter: Counter[str] | None) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _required_value_for_blocker(code: str, missing: str | None) -> str:
    if code == "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD":
        return f"opportunity_score >= {PAPER_THRESHOLD}"
    if missing:
        return missing
    mapping = {
        "EXISTING_HARD_BLOCKERS_PRESENT": "all existing hard blockers cleared",
        "THESIS_NOT_SUPPORTED": "supported_trade_thesis",
        "EXIT_NOT_READY": "exit_plan",
        "EDGE_NOT_SUPPORTED": "source_backed_edge",
        "DECISION_BAND_NOT_PAPER_OBSERVATION": "decision_band PAPER_OBSERVATION",
        "OBSERVATION_POLICY_NOT_ALLOWED": "observation_policy_state eligible",
    }
    return mapping.get(code, f"clear {code}")


def _actionable_for_blocker(code: str, observed_action: str | None, meta: dict[str, Any]) -> str:
    if code in BLOCKER_MAP:
        return str(meta["actionable"])
    return observed_action or str(meta["actionable"])


def _audit_tables(tables: dict[str, set[str]]) -> dict[str, str]:
    return {
        "paper_ready_decisions": "paper_observation_policy_reviews",
        "runtime_paper_decisions": "paper_runtime_decisions",
        "policy_reviews": "paper_observation_policy_reviews",
        "final_blockers": "paper_runtime_decisions.blockers_json / no_trade_log.blockers",
        "no_trade_reasons": "no_trade_log",
        "paper_intents": "paper_intents",
        "paper_orders": "paper_orders",
        "paper_fills": "paper_fills",
        "paper_positions": "paper_positions",
        "position_closes": "paper_position_closes",
        "paper_sessions": "paper_sessions",
    }


def _service_map() -> dict[str, str]:
    return {
        "policy_to_runtime_decision": "PaperRuntimeDecisionService",
        "enter_watch_block": "PaperRuntimeDecisionService",
        "paper_intent": "PaperIntentGateService",
        "paper_order_fill_position": "PaperExecutionService",
        "paper_position_close": "PaperExitLoopService",
    }


def _tables(conn: Any) -> dict[str, set[str]]:
    rows = conn.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema=current_schema()").fetchall()
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return out


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _float(value: Any) -> float:
    return float(_decimal(value))


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0
