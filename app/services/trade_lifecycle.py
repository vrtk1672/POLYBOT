from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.risk_evidence_mesh import RiskEvidenceMeshService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
SUBJECT_TYPES = {"FRESH_SEED", "PAPER_CANDIDATE", "PAPER_INTENT", "PAPER_POSITION"}
STRATEGY_TYPES = {
    "REPRICING_CANDIDATE",
    "HOLD_TO_RESOLUTION_CANDIDATE",
    "EXIT_NOW_REVIEW",
    "HOLD_REVIEW",
    "CAPITAL_EFFICIENCY_PLAY",
    "WATCH_ONLY",
    "NO_TRADE",
    "INSUFFICIENT_DATA",
    "RISK_BLOCKED",
    "EXIT_BLOCKED",
    "CAPITAL_BLOCKED",
    "SAME_MARKET_BLOCKED",
    "UNKNOWN",
}
PLAN_STATUSES = {"COMPLETE", "PARTIAL", "WATCH", "NO_TRADE", "BLOCKED", "INSUFFICIENT_DATA"}
DECISION_CLASSES = {
    "PAPER_CANDIDATE_REVIEW",
    "PAPER_INTENT_READY_CONTEXT",
    "HOLD_REVIEW",
    "EXIT_REVIEW",
    "NO_TRADE",
    "WATCH",
    "BLOCKED",
    "INSUFFICIENT_DATA",
}
CORE_REQUIRED = {
    "PAYOUT_ODDS",
    "EXIT_HOLD",
    "CAPITAL_EFFICIENCY",
    "RISK",
    "EXIT_FOUNDATION",
    "ORDERBOOK_LIQUIDITY",
    "COORDINATOR",
}


class TradeLifecycleService:
    """Source-backed lifecycle planning mesh.

    The service writes only derived lifecycle records. It does not create paper
    intents, orders, fills, positions, closes, capital ledger rows, or balance
    mutations.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def build_recent(self, *, limit: int = 100, subject_type: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "plans_created": 0}
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "plans_created": 0}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "plans_created": 0}
            before = _count_table(conn, "trade_lifecycle_plans")
            safety_before = _safety_counts(conn)
            records = self._records(conn, subject_type=subject, limit=limit)
            outcomes = [self._build_record(conn, record, dry_run=dry_run) for record in records]
            after = _count_table(conn, "trade_lifecycle_plans")
            safety_after = _safety_counts(conn)
        status_counts = Counter(item["plan_status"] for item in outcomes)
        strategy_counts = Counter(item["strategy_type"] for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "plans_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_status": dict(status_counts),
                "outcomes_by_strategy_type": dict(strategy_counts),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": safety_before != safety_after,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def build_subject_with_conn(self, conn: Any, *, subject_type: str, subject_id: str, dry_run: bool = False) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"status": "MISSING_TABLES", "subject_type": subject_type, "subject_id": subject_id}
        subject = str(subject_type).upper()
        if subject not in SUBJECT_TYPES:
            return {"status": "INVALID_SUBJECT_TYPE", "subject_type": subject_type, "subject_id": subject_id}
        record = self._record_by_subject(conn, subject_type=subject, subject_id=subject_id)
        if record is None:
            return {"status": "SUBJECT_NOT_FOUND", "subject_type": subject, "subject_id": subject_id}
        return self._build_record(conn, record, dry_run=dry_run)

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty_dashboard("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trade_lifecycle_plans"):
                return _empty_dashboard("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE plan_status='COMPLETE') AS complete_count,
                    COUNT(*) FILTER (WHERE plan_status='PARTIAL') AS partial_count,
                    COUNT(*) FILTER (WHERE plan_status='WATCH') AS watch_count,
                    COUNT(*) FILTER (WHERE plan_status='NO_TRADE') AS no_trade_count,
                    COUNT(*) FILTER (WHERE plan_status='BLOCKED') AS blocked_count,
                    COUNT(*) FILTER (WHERE plan_status='INSUFFICIENT_DATA') AS insufficient_count
                FROM trade_lifecycle_plans
                """,
            ) or {}
            by_subject = _fetchall(conn, "SELECT subject_type, COUNT(*) AS count FROM trade_lifecycle_plans GROUP BY subject_type ORDER BY subject_type")
            by_strategy = _fetchall(conn, "SELECT strategy_type, COUNT(*) AS count FROM trade_lifecycle_plans GROUP BY strategy_type ORDER BY strategy_type")
            by_status = _fetchall(conn, "SELECT plan_status, COUNT(*) AS count FROM trade_lifecycle_plans GROUP BY plan_status ORDER BY plan_status")
            latest = _latest_rows(conn, limit=limit)
            top_missing = _fetchall(
                conn,
                """
                SELECT value AS missing_input, COUNT(*) AS count
                FROM trade_lifecycle_plans, jsonb_array_elements_text(missing_inputs_json) AS value
                GROUP BY value
                ORDER BY count DESC, missing_input
                LIMIT %s
                """,
                (limit,),
            )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_plans": _int(totals.get("total")),
                "plans_by_subject_type": {str(row["subject_type"]): _int(row["count"]) for row in by_subject},
                "plans_by_strategy_type": {str(row["strategy_type"]): _int(row["count"]) for row in by_strategy},
                "plans_by_status": {str(row["plan_status"]): _int(row["count"]) for row in by_status},
                "complete_plans": _int(totals.get("complete_count")),
                "partial_plans": _int(totals.get("partial_count")),
                "watch_plans": _int(totals.get("watch_count")),
                "no_trade_plans": _int(totals.get("no_trade_count")),
                "blocked_plans": _int(totals.get("blocked_count")),
                "insufficient_data_plans": _int(totals.get("insufficient_count")),
                "latest_plans": latest,
                "top_missing_inputs": top_missing,
            }
        )

    def detail(self, plan_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "plan_id": plan_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "trade_lifecycle_plans"):
                return {"mock_data": False, "status": "MISSING_TABLES", "plan_id": plan_id}
            plan = _fetchone(conn, "SELECT * FROM trade_lifecycle_plans WHERE plan_id=%s", (plan_id,))
            if not plan:
                return {"mock_data": False, "status": "NOT_FOUND", "plan_id": plan_id}
            sources = _fetchall(conn, "SELECT * FROM trade_lifecycle_plan_sources WHERE plan_id=%s ORDER BY linked_at,id", (plan_id,))
            contributions = _fetchall(conn, "SELECT * FROM trade_lifecycle_brain_contributions WHERE plan_id=%s ORDER BY created_at,id", (plan_id,))
            related = _related_subject(conn, plan)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "plan": plan,
                "brain_contributions": contributions,
                "sources": sources,
                "related_subject": related,
                "forensics_link": f"/dashboard/api/v2/paper/trade-forensics/{plan['subject_id']}" if plan.get("subject_type") == "PAPER_POSITION" else None,
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "trade_lifecycle_plans"):
            return None
        return _fetchone(
            conn,
            """
            SELECT * FROM trade_lifecycle_plans
            WHERE subject_type=%s AND subject_id=%s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC, id DESC LIMIT 1
            """,
            (subject_type, subject_id),
        )

    def observational_summary_for_market(
        self,
        conn: Any,
        *,
        market_id: str | None = None,
        position_id: str | None = None,
        candidate_id: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        if not _table_exists(conn, "trade_lifecycle_plans"):
            return {"status": "MISSING_TABLES", "latest_plans": [], "observational_only": True}
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id=%s")
            params.append(str(market_id))
        if position_id:
            clauses.append("subject_id=%s")
            params.append(str(position_id))
        if candidate_id:
            clauses.append("subject_id=%s")
            params.append(str(candidate_id))
        where = " OR ".join(clauses) if clauses else "TRUE"
        params.append(limit)
        rows = _fetchall(
            conn,
            f"""
            SELECT plan_id,subject_type,subject_id,market_id,side,strategy_type,plan_status,decision_class,
                   missing_inputs_json,created_at,updated_at
            FROM trade_lifecycle_plans
            WHERE {where}
            ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT %s
            """,
            tuple(params),
        )
        return _json_safe({"status": "OK", "latest_plans": rows, "observational_only": True})

    def _records(self, conn: Any, *, subject_type: str | None, limit: int) -> list[dict[str, Any]]:
        wanted = [subject_type] if subject_type else ["PAPER_POSITION", "PAPER_INTENT", "PAPER_CANDIDATE", "FRESH_SEED"]
        rows: list[dict[str, Any]] = []
        if "PAPER_POSITION" in wanted:
            rows.extend(_position_records(conn, limit=limit))
        if "PAPER_INTENT" in wanted:
            rows.extend(_intent_records(conn, limit=limit))
        if "PAPER_CANDIDATE" in wanted:
            rows.extend(_candidate_records(conn, limit=limit))
        if "FRESH_SEED" in wanted:
            rows.extend(_fresh_seed_records(conn, limit=limit))
        return rows

    def _record_by_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if subject_type == "PAPER_POSITION":
            rows = _position_records(conn, limit=1, subject_id=subject_id)
        elif subject_type == "PAPER_INTENT":
            rows = _intent_records(conn, limit=1, subject_id=subject_id)
        elif subject_type == "PAPER_CANDIDATE":
            rows = _candidate_records(conn, limit=1, subject_id=subject_id)
        else:
            rows = _fresh_seed_records(conn, limit=1, subject_id=subject_id)
        return rows[0] if rows else None

    def _build_record(self, conn: Any, record: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        evidence = _collect_evidence(conn, record)
        summaries = _summaries(record, evidence)
        missing = _missing_inputs(record, evidence, summaries)
        strategy_type, plan_status, decision_class = _classify_plan(record, evidence, missing)
        plan = {
            "plan_id": _plan_id(record, evidence, strategy_type, plan_status, decision_class),
            "subject_type": record["subject_type"],
            "subject_id": record["subject_id"],
            "market_id": record.get("market_id") or _first_nonempty(
                (evidence.get("payout") or {}).get("market_id"),
                (evidence.get("exit_hold") or {}).get("market_id"),
                (evidence.get("capital_efficiency") or {}).get("market_id"),
            ),
            "condition_id": record.get("condition_id") or (evidence.get("payout") or {}).get("condition_id"),
            "side": record.get("side") or (evidence.get("payout") or {}).get("side"),
            "token_id": record.get("token_id") or (evidence.get("payout") or {}).get("token_id") or (evidence.get("exit_hold") or {}).get("token_id"),
            "mesh_session_id": (evidence.get("session") or {}).get("session_id"),
            "strategy_type": strategy_type,
            "plan_status": plan_status,
            "decision_class": decision_class,
            "economic_thesis": _economic_thesis(evidence),
            "entry_thesis": _entry_thesis(record, evidence),
            "exit_thesis": _exit_thesis(evidence),
            "hold_to_resolution_thesis": _hold_thesis(evidence),
            "invalidation_rules_json": _invalidation_rules(evidence, missing),
            "capital_plan_json": summaries["capital_plan"],
            "monitoring_plan_json": _monitoring_plan(record, evidence, missing),
            "risk_summary_json": summaries["risk"],
            "liquidity_summary_json": summaries["liquidity"],
            "payout_summary_json": summaries["payout"],
            "exit_hold_summary_json": summaries["exit_hold"],
            "capital_efficiency_summary_json": summaries["capital_efficiency"],
            "same_market_summary_json": summaries["same_market"],
            "coordinator_judgment_json": summaries["coordinator"],
            "missing_inputs_json": sorted(set(missing)),
            "source_refs_json": _source_refs(evidence),
            "metadata_json": {
                "observational_only": True,
                "derived_truth_only": True,
                "no_trading_mutation": True,
                "no_fake_thesis": True,
                "no_fake_confidence": True,
                "no_fake_fair_probability": True,
                "source_refresh_cycle_id": ((evidence.get("risk_evidence") or {}).get("metadata_json") or {}).get("source_refresh_cycle_id"),
                "propagation_context": (((evidence.get("risk_evidence") or {}).get("metadata_json") or {}).get("propagation_context") or {}),
                "risk_evidence_id": (evidence.get("risk_evidence") or {}).get("evaluation_id"),
            },
        }
        sources = _sources(record, evidence)
        contributions = _brain_contributions(evidence, missing)
        if not dry_run:
            _upsert_plan(conn, plan, sources, contributions)
        return _json_safe(
            {
                "plan_id": plan["plan_id"],
                "subject_type": record["subject_type"],
                "subject_id": record["subject_id"],
                "strategy_type": strategy_type,
                "plan_status": plan_status,
                "decision_class": decision_class,
                "missing_inputs": plan["missing_inputs_json"],
                "brain_contributions": len(contributions),
                "dry_run": dry_run,
            }
        )


def _position_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    where = "WHERE pp.id::text=%s" if subject_id else "WHERE pp.current_status IN ('OPEN','EXIT_PENDING') AND pp.closed_at IS NULL AND COALESCE(pp.excluded_from_active_paper_truth,false)=false"
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'PAPER_POSITION' AS subject_type, pp.id::text AS subject_id, pp.id::text AS paper_position_id,
               pp.market_id, pp.intended_outcome AS side, pp.avg_entry AS entry_price, pp.size AS quantity,
               pp.opened_at, pp.payload_json, mv.condition_id, NULL::text AS token_id,
               (pp.payload_json->>'risk_decision_id') AS risk_decision_id,
               (pp.payload_json->>'exit_plan_id') AS exit_plan_id,
               (pp.payload_json->>'source_intent_id') AS paper_intent_id,
               NULLIF((pp.payload_json->>'orderbook_snapshot_id'),'') AS orderbook_snapshot_id,
               (pp.payload_json->>'correlation_id') AS correlation_id
        FROM paper_positions pp
        LEFT JOIN markets_v2 mv ON mv.market_id=pp.market_id
        {where}
        ORDER BY pp.opened_at DESC NULLS LAST, pp.id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _intent_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    where = "WHERE paper_intent_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'PAPER_INTENT' AS subject_type, paper_intent_id AS subject_id, NULL::text AS paper_position_id,
               market_id, side, intended_price AS entry_price, NULL::numeric AS quantity, created_at AS opened_at,
               evidence AS payload_json, NULL::text AS condition_id, NULL::text AS token_id,
               risk_decision_id, exit_plan_id, paper_intent_id, orderbook_snapshot_id::text, NULL::text AS correlation_id,
               eligibility_id, coordinator_decision_id, intent_status
        FROM paper_intents
        {where}
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _candidate_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    where = "WHERE pec.eligibility_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(
        conn,
        f"""
        SELECT 'PAPER_CANDIDATE' AS subject_type,
               pec.eligibility_id AS subject_id,
               NULL::text AS paper_position_id,
               pec.market_id,
               pec.side,
               NULL::numeric AS entry_price,
               NULL::numeric AS quantity,
               pec.updated_at AS opened_at,
               pec.evidence AS payload_json,
               mv2.condition_id AS condition_id,
               COALESCE(
                   NULLIF(pec.expected_token_id, ''),
                   NULLIF(obs.token_id, ''),
                   CASE
                       WHEN upper(pec.side) = 'YES' THEN NULLIF(mv2.yes_token_id, '')
                       WHEN upper(pec.side) = 'NO' THEN NULLIF(mv2.no_token_id, '')
                       ELSE NULL
                   END
               ) AS token_id,
               pec.risk_decision_id,
               COALESCE(exit_candidate.exit_plan_id, pec.exit_plan_id) AS exit_plan_id,
               NULL::text AS paper_intent_id,
               COALESCE(obs.id::text, pec.orderbook_snapshot_id::text) AS orderbook_snapshot_id,
               obs.correlation_id AS correlation_id,
               pec.coordinator_decision_id,
               pec.status
        FROM paper_eligibility_candidates pec
        LEFT JOIN markets_v2 mv2 ON mv2.market_id = pec.market_id
        LEFT JOIN LATERAL (
            SELECT book.*
            FROM orderbook_snapshots book
            WHERE (
                    pec.orderbook_snapshot_id IS NOT NULL
                    AND (book.id::text = pec.orderbook_snapshot_id::text OR book.orderbook_snapshot_id = pec.orderbook_snapshot_id::text)
                  )
               OR book.metadata_json->>'candidate_id' = pec.eligibility_id
            ORDER BY COALESCE(book.collected_at, book.snapshot_at, book.created_at) DESC, book.id DESC
            LIMIT 1
        ) obs ON true
        LEFT JOIN LATERAL (
            SELECT ep.exit_plan_id
            FROM exit_plans ep
            WHERE ep.exit_plan_id = 'exit_candidate_' || pec.eligibility_id
            ORDER BY ep.updated_at DESC NULLS LAST, ep.id DESC
            LIMIT 1
        ) exit_candidate ON true
        {where}
        ORDER BY pec.updated_at DESC, pec.id DESC
        LIMIT %s
        """,
        tuple(params),
    )
    for row in rows:
        evidence = _dict(row.get("payload_json"))
        row["entry_price"] = _decimal_or_none(evidence.get("orderbook_best_ask") or _dict(evidence.get("source_evidence")).get("orderbook_best_ask"))
        row["quantity"] = _decimal_or_none(evidence.get("quantity"))
    return rows


def _fresh_seed_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fresh_candidate_seeds"):
        return []
    where = "WHERE seed_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'FRESH_SEED' AS subject_type, seed_id AS subject_id, NULL::text AS paper_position_id,
               market_id, side, NULL::numeric AS entry_price, NULL::numeric AS quantity, created_at AS opened_at,
               metadata_json AS payload_json, condition_id, expected_token_id AS token_id, NULL::text AS risk_decision_id,
               NULL::text AS exit_plan_id, NULL::text AS paper_intent_id, NULL::text AS orderbook_snapshot_id,
               NULL::text AS correlation_id, NULL::text AS coordinator_decision_id
        FROM fresh_candidate_seeds
        {where}
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _collect_evidence(conn: Any, record: dict[str, Any]) -> dict[str, Any]:
    market_id = _text(record.get("market_id"))
    position_id = _text(record.get("paper_position_id"))
    candidate_id = record["subject_id"] if record["subject_type"] in {"FRESH_SEED", "PAPER_CANDIDATE"} else _text(record.get("eligibility_id"))
    session = _latest_session(conn, record, market_id=market_id, position_id=position_id, candidate_id=candidate_id)
    session_id = _text((session or {}).get("session_id"))
    return {
        "payout": _latest_payout(conn, record),
        "exit_hold": _latest_exit_hold(conn, record),
        "capital_efficiency": _latest_capital_efficiency(conn, record),
        "same_market_guard": _latest_guard(conn, record),
        "risk": _latest_risk(conn, record, market_id=market_id),
        "risk_evidence": _latest_risk_evidence(conn, record),
        "exit_plan": _latest_exit_plan(conn, record, market_id=market_id),
        "capital_brain": _latest_capital_brain(conn, record, session_id=session_id, market_id=market_id, position_id=position_id, candidate_id=candidate_id),
        "session": session,
        "awareness": _latest_awareness(conn, session_id),
        "opinions": _latest_opinions(conn, session_id),
        "coordinator": _latest_coordinator(conn, record, session_id=session_id, market_id=market_id, position_id=position_id, candidate_id=candidate_id),
        "conflicts": _latest_conflicts(conn, session_id),
        "orderbook": _latest_orderbook(conn, record, market_id=market_id),
        "position_awareness": _latest_position_awareness(conn, position_id),
        "position_reactions": _latest_position_reactions(conn, position_id),
        "watchdog_trace": _latest_watchdog_trace(conn, position_id),
        "rules": _latest_rules(conn, market_id),
        "news": _latest_news(conn, market_id),
        "whale": _latest_whale(conn, market_id),
        "memory": _latest_memory(conn, market_id),
    }


def _latest_payout(conn: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "payout_odds_evaluations"):
        return None
    return _fetchone(
        conn,
        "SELECT * FROM payout_odds_evaluations WHERE subject_type=%s AND subject_id=%s ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT 1",
        (record["subject_type"], record["subject_id"]),
    )


def _latest_exit_hold(conn: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "exit_hold_evaluations"):
        return None
    if record["subject_type"] not in {"PAPER_POSITION", "PAPER_CANDIDATE", "PAPER_INTENT"}:
        return None
    return _fetchone(
        conn,
        "SELECT * FROM exit_hold_evaluations WHERE subject_type=%s AND subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (record["subject_type"], record["subject_id"]),
    )


def _latest_capital_efficiency(conn: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "capital_efficiency_evaluations"):
        return None
    return _fetchone(
        conn,
        "SELECT * FROM capital_efficiency_evaluations WHERE subject_type=%s AND subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1",
        (record["subject_type"], record["subject_id"]),
    )


def _latest_guard(conn: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "same_market_side_guard_decisions"):
        return None
    clauses = []
    params: list[Any] = []
    if record["subject_type"] == "PAPER_INTENT":
        clauses.append("proposed_intent_id=%s")
        params.append(record["subject_id"])
    if record["subject_type"] in {"PAPER_CANDIDATE", "FRESH_SEED"}:
        clauses.append("proposed_candidate_id=%s")
        params.append(record["subject_id"])
    if record.get("market_id") and record.get("side"):
        clauses.append("(market_id=%s AND proposed_side=%s)")
        params.extend([str(record["market_id"]), str(record["side"]).upper()])
    if not clauses:
        return None
    return _fetchone(conn, f"SELECT * FROM same_market_side_guard_decisions WHERE {' OR '.join(clauses)} ORDER BY created_at DESC,id DESC LIMIT 1", tuple(params))


def _latest_risk(conn: Any, record: dict[str, Any], *, market_id: str | None) -> dict[str, Any] | None:
    if not _table_exists(conn, "risk_decisions"):
        return None
    risk_id = _text(record.get("risk_decision_id"))
    if risk_id:
        row = _fetchone(conn, "SELECT * FROM risk_decisions WHERE risk_decision_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (risk_id,))
        if row:
            return row
    if market_id:
        return _fetchone(conn, "SELECT * FROM risk_decisions WHERE market_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (market_id,))
    return None


def _latest_risk_evidence(conn: Any, record: dict[str, Any]) -> dict[str, Any] | None:
    return RiskEvidenceMeshService().latest_for_subject(conn, subject_type=record["subject_type"], subject_id=record["subject_id"])


def _latest_exit_plan(conn: Any, record: dict[str, Any], *, market_id: str | None) -> dict[str, Any] | None:
    if not _table_exists(conn, "exit_plans"):
        return None
    exit_id = _text(record.get("exit_plan_id"))
    if exit_id:
        row = _fetchone(conn, "SELECT * FROM exit_plans WHERE exit_plan_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (exit_id,))
        if row:
            return row
    risk_id = _text(record.get("risk_decision_id"))
    if risk_id:
        row = _fetchone(conn, "SELECT * FROM exit_plans WHERE risk_decision_ref=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (risk_id,))
        if row:
            return row
    if market_id:
        params: list[Any] = [market_id]
        side_clause = ""
        if record.get("side"):
            side_clause = " AND (side IS NULL OR side=%s)"
            params.append(str(record["side"]).upper())
        return _fetchone(conn, f"SELECT * FROM exit_plans WHERE market_id=%s{side_clause} ORDER BY updated_at DESC,id DESC LIMIT 1", tuple(params))
    return None


def _latest_capital_brain(
    conn: Any,
    record: dict[str, Any],
    *,
    session_id: str | None,
    market_id: str | None,
    position_id: str | None,
    candidate_id: str | None,
) -> dict[str, Any] | None:
    if not _table_exists(conn, "capital_brain_evaluations"):
        return None
    if session_id:
        row = _fetchone(conn, "SELECT * FROM capital_brain_evaluations WHERE session_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (session_id,))
        if row:
            return row
    clauses: list[str] = []
    params: list[Any] = []
    if position_id:
        clauses.append("position_id=%s")
        params.append(position_id)
    if candidate_id:
        clauses.append("candidate_id=%s")
        params.append(candidate_id)
    if market_id:
        clauses.append("market_id=%s")
        params.append(market_id)
    if not clauses:
        return None
    return _fetchone(conn, f"SELECT * FROM capital_brain_evaluations WHERE {' OR '.join(clauses)} ORDER BY created_at DESC,id DESC LIMIT 1", tuple(params))


def _latest_session(conn: Any, record: dict[str, Any], *, market_id: str | None, position_id: str | None, candidate_id: str | None) -> dict[str, Any] | None:
    if not _table_exists(conn, "mesh_sessions"):
        return None
    coordinator_id = _text(record.get("coordinator_decision_id"))
    if coordinator_id and _table_exists(conn, "mesh_coordinator_decisions"):
        row = _fetchone(
            conn,
            """
            SELECT ms.*
            FROM mesh_coordinator_decisions md
            JOIN mesh_sessions ms ON ms.session_id=md.session_id
            WHERE md.decision_id=%s
            ORDER BY md.created_at DESC, md.id DESC LIMIT 1
            """,
            (coordinator_id,),
        )
        if row:
            return row
    clauses: list[str] = []
    params: list[Any] = []
    if position_id:
        clauses.append("position_id=%s")
        params.append(position_id)
    if candidate_id:
        clauses.append("candidate_id=%s")
        params.append(candidate_id)
    if market_id:
        clauses.append("market_id=%s")
        params.append(market_id)
    if not clauses:
        return None
    return _fetchone(conn, f"SELECT * FROM mesh_sessions WHERE {' OR '.join(clauses)} ORDER BY opened_at DESC,id DESC LIMIT 1", tuple(params))


def _latest_awareness(conn: Any, session_id: str | None) -> dict[str, Any] | None:
    if not session_id or not _table_exists(conn, "mesh_shared_awareness"):
        return None
    return _fetchone(conn, "SELECT * FROM mesh_shared_awareness WHERE session_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (session_id,))


def _latest_opinions(conn: Any, session_id: str | None) -> list[dict[str, Any]]:
    if not session_id or not _table_exists(conn, "mesh_brain_opinions"):
        return []
    return _fetchall(conn, "SELECT * FROM mesh_brain_opinions WHERE session_id=%s ORDER BY created_at DESC,id DESC LIMIT 20", (session_id,))


def _latest_coordinator(
    conn: Any,
    record: dict[str, Any],
    *,
    session_id: str | None,
    market_id: str | None,
    position_id: str | None,
    candidate_id: str | None,
) -> dict[str, Any] | None:
    if not _table_exists(conn, "mesh_coordinator_decisions"):
        return None
    coordinator_id = _text(record.get("coordinator_decision_id"))
    if coordinator_id:
        row = _fetchone(conn, "SELECT * FROM mesh_coordinator_decisions WHERE decision_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (coordinator_id,))
        if row:
            return row
    if session_id:
        row = _fetchone(conn, "SELECT * FROM mesh_coordinator_decisions WHERE session_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (session_id,))
        if row:
            return row
    clauses: list[str] = []
    params: list[Any] = []
    if position_id:
        clauses.append("position_id=%s")
        params.append(position_id)
    if candidate_id:
        clauses.append("candidate_id=%s")
        params.append(candidate_id)
    if market_id:
        clauses.append("market_id=%s")
        params.append(market_id)
    if not clauses:
        return None
    return _fetchone(conn, f"SELECT * FROM mesh_coordinator_decisions WHERE {' OR '.join(clauses)} ORDER BY created_at DESC,id DESC LIMIT 1", tuple(params))


def _latest_conflicts(conn: Any, session_id: str | None) -> list[dict[str, Any]]:
    if not session_id or not _table_exists(conn, "mesh_conflict_records"):
        return []
    return _fetchall(conn, "SELECT * FROM mesh_conflict_records WHERE session_id=%s ORDER BY created_at DESC,id DESC LIMIT 10", (session_id,))


def _latest_orderbook(conn: Any, record: dict[str, Any], *, market_id: str | None) -> dict[str, Any] | None:
    if not _table_exists(conn, "orderbook_snapshots"):
        return None
    snapshot_id = _text(record.get("orderbook_snapshot_id"))
    if snapshot_id:
        row = _fetchone(conn, "SELECT * FROM orderbook_snapshots WHERE id::text=%s OR orderbook_snapshot_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (snapshot_id, snapshot_id))
        if row:
            return row
    if market_id:
        params: list[Any] = [market_id]
        side_clause = ""
        if record.get("side"):
            side_clause = " AND (side IS NULL OR side=%s)"
            params.append(str(record["side"]).upper())
        return _fetchone(conn, f"SELECT * FROM orderbook_snapshots WHERE market_id=%s{side_clause} ORDER BY collected_at DESC,created_at DESC,id DESC LIMIT 1", tuple(params))
    return None


def _latest_position_awareness(conn: Any, position_id: str | None) -> dict[str, Any] | None:
    if not position_id or not _table_exists(conn, "position_awareness"):
        return None
    return _fetchone(conn, "SELECT * FROM position_awareness WHERE position_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (position_id,))


def _latest_position_reactions(conn: Any, position_id: str | None) -> list[dict[str, Any]]:
    if not position_id or not _table_exists(conn, "position_reactions"):
        return []
    return _fetchall(conn, "SELECT * FROM position_reactions WHERE position_id=%s ORDER BY created_at DESC,id DESC LIMIT 10", (position_id,))


def _latest_watchdog_trace(conn: Any, position_id: str | None) -> dict[str, Any] | None:
    if not position_id or not _table_exists(conn, "open_position_watchdog_traces"):
        return None
    return _fetchone(conn, "SELECT * FROM open_position_watchdog_traces WHERE paper_position_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (position_id,))


def _latest_rules(conn: Any, market_id: str | None) -> dict[str, Any] | None:
    if not market_id:
        return None
    if _table_exists(conn, "rules_analysis"):
        row = _fetchone(conn, "SELECT * FROM rules_analysis WHERE market_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (market_id,))
        if row:
            row["_source_table"] = "rules_analysis"
            row["_source_record_id"] = row.get("rules_analysis_id")
            return row
    if _table_exists(conn, "market_rules"):
        row = _fetchone(conn, "SELECT * FROM market_rules WHERE market_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (market_id,))
        if row:
            row["_source_table"] = "market_rules"
            row["_source_record_id"] = row.get("market_id")
            return row
    return None


def _latest_news(conn: Any, market_id: str | None) -> dict[str, Any] | None:
    if not market_id:
        return None
    if _table_exists(conn, "news_impact_scores"):
        return _fetchone(conn, "SELECT * FROM news_impact_scores WHERE market_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (market_id,))
    if _table_exists(conn, "news_market_links"):
        return _fetchone(conn, "SELECT * FROM news_market_links WHERE market_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (market_id,))
    return None


def _latest_whale(conn: Any, market_id: str | None) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, "whale_events"):
        return None
    return _fetchone(conn, "SELECT * FROM whale_events WHERE market_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (market_id,))


def _latest_memory(conn: Any, market_id: str | None) -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, "market_memory_v2"):
        return None
    return _fetchone(conn, "SELECT * FROM market_memory_v2 WHERE market_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (market_id,))


def _summaries(record: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    payout = ev.get("payout") or {}
    exit_hold = ev.get("exit_hold") or {}
    cap = ev.get("capital_efficiency") or {}
    guard = ev.get("same_market_guard") or {}
    risk = ev.get("risk") or {}
    risk_evidence = ev.get("risk_evidence") or {}
    exit_plan = ev.get("exit_plan") or {}
    book = ev.get("orderbook") or {}
    coordinator = ev.get("coordinator") or {}
    capital_brain = ev.get("capital_brain") or {}
    rules = ev.get("rules") or {}
    return {
        "payout": {
            "evaluation_id": payout.get("evaluation_id"),
            "price": payout.get("price"),
            "implied_probability": payout.get("implied_probability"),
            "risk_reward": payout.get("risk_reward"),
            "profit_if_win": payout.get("profit_if_win"),
            "max_loss": payout.get("max_loss"),
            "fair_probability": payout.get("fair_probability"),
            "expected_value": payout.get("expected_value"),
        },
        "exit_hold": {
            "evaluation_id": exit_hold.get("evaluation_id"),
            "decision": exit_hold.get("decision"),
            "exit_now_value": exit_hold.get("exit_now_value"),
            "exit_now_pnl": exit_hold.get("exit_now_pnl"),
            "hold_to_resolution_value": exit_hold.get("hold_to_resolution_value"),
            "hold_to_resolution_profit_if_win": exit_hold.get("hold_to_resolution_profit_if_win"),
            "time_to_resolution_seconds": exit_hold.get("time_to_resolution_seconds"),
            "rules_risk": exit_hold.get("rules_risk"),
            "risk_of_reversal": exit_hold.get("risk_of_reversal"),
            "missing_inputs": exit_hold.get("missing_inputs_json"),
        },
        "capital_efficiency": {
            "evaluation_id": cap.get("evaluation_id"),
            "recommendation": cap.get("recommendation"),
            "capital_locked": cap.get("capital_locked"),
            "reward_per_dollar_hour": cap.get("reward_per_dollar_hour"),
            "capital_efficiency_score": cap.get("capital_efficiency_score"),
            "missing_inputs": cap.get("missing_inputs_json"),
        },
        "capital_plan": {
            "capital_required_or_locked": cap.get("capital_locked") or payout.get("stake_usd"),
            "capital_brain_decision": capital_brain.get("decision"),
            "capital_efficiency_recommendation": cap.get("recommendation"),
            "reward_per_dollar_hour": cap.get("reward_per_dollar_hour"),
            "observational_only": True,
        },
        "same_market": {
            "decision_id": guard.get("decision_id"),
            "decision": guard.get("decision"),
            "blocker_reason": guard.get("blocker_reason"),
            "source_backed_rationale": guard.get("source_backed"),
            "rationale_type": guard.get("rationale_type"),
        },
        "risk": {
            "risk_decision_id": risk.get("risk_decision_id"),
            "decision": risk.get("decision"),
            "risk_status": risk.get("risk_status"),
            "risk_score": risk.get("risk_score"),
            "risk_approved": risk.get("risk_approved"),
            "blockers": risk.get("blockers"),
            "warnings": risk.get("warnings"),
            "risk_evidence_mesh": {
                "evaluation_id": risk_evidence.get("evaluation_id"),
                "risk_decision": risk_evidence.get("risk_decision"),
                "risk_blocker_subtype": risk_evidence.get("risk_blocker_subtype"),
                "edge_source_type": risk_evidence.get("edge_source_type"),
                "edge_status": risk_evidence.get("edge_status"),
                "source_refresh_cycle_id": (risk_evidence.get("metadata_json") or {}).get("source_refresh_cycle_id") if isinstance(risk_evidence.get("metadata_json"), dict) else None,
                "edge_thesis_id": ((risk_evidence.get("metadata_json") or {}).get("edge_thesis") or {}).get("edge_thesis_id") if isinstance(risk_evidence.get("metadata_json"), dict) else None,
                "critical_missing": risk_evidence.get("critical_evidence_missing_json"),
                "optional_missing": risk_evidence.get("optional_context_missing_json"),
                "blocking_evidence": risk_evidence.get("blocking_evidence_json"),
            },
        },
        "liquidity": {
            "orderbook_snapshot_id": book.get("orderbook_snapshot_id") or book.get("id"),
            "best_bid": book.get("best_bid"),
            "best_ask": book.get("best_ask"),
            "spread": book.get("spread"),
            "liquidity_score": book.get("liquidity_score"),
            "snapshot_status": book.get("snapshot_status"),
            "is_stale": book.get("is_stale"),
        },
        "coordinator": {
            "decision_id": coordinator.get("decision_id"),
            "session_id": coordinator.get("session_id"),
            "final_stance": coordinator.get("final_stance"),
            "final_action": coordinator.get("final_action"),
            "decision_reason": coordinator.get("decision_reason"),
            "conflicts_detected": coordinator.get("conflicts_detected"),
            "conflict_count": coordinator.get("conflict_count"),
        },
        "exit_foundation": {
            "exit_plan_id": exit_plan.get("exit_plan_id"),
            "status": exit_plan.get("status") or exit_plan.get("plan_status"),
            "exit_type": exit_plan.get("exit_type"),
            "target_exit": exit_plan.get("target_exit"),
            "stop_loss": exit_plan.get("stop_loss"),
            "max_hold_seconds": exit_plan.get("max_hold_seconds"),
            "blockers": exit_plan.get("blockers"),
        },
        "rules": {
            "source": rules.get("_source_table"),
            "recommendation": rules.get("recommendation"),
            "wording_risk": rules.get("wording_risk"),
            "dispute_risk": rules.get("dispute_risk"),
            "source_verification_status": rules.get("source_verification_status"),
        },
    }


def _missing_inputs(record: dict[str, Any], ev: dict[str, Any], summaries: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not ev.get("payout"):
        missing.append("PAYOUT_ODDS_MISSING")
    elif (ev["payout"].get("fair_probability") is None):
        missing.append("FAIR_PROBABILITY_MISSING")
    if not ev.get("exit_hold"):
        missing.append("EXIT_HOLD_MISSING")
    else:
        missing.extend(_list(ev["exit_hold"].get("missing_inputs_json")))
    if not ev.get("capital_efficiency"):
        missing.append("CAPITAL_EFFICIENCY_MISSING")
    else:
        missing.extend(_list(ev["capital_efficiency"].get("missing_inputs_json")))
    if not ev.get("same_market_guard"):
        missing.append("SAME_MARKET_GUARD_MISSING")
    if not ev.get("risk"):
        missing.append("RISK_DECISION_MISSING")
    if not ev.get("exit_plan"):
        missing.append("EXIT_PLAN_MISSING")
    if not ev.get("capital_brain"):
        missing.append("CAPITAL_BRAIN_MISSING")
    if not ev.get("coordinator"):
        missing.append("COORDINATOR_DECISION_MISSING")
    if not ev.get("orderbook"):
        missing.append("ORDERBOOK_LIQUIDITY_MISSING")
    if not ev.get("rules"):
        missing.append("RULES_WORDING_MISSING")
    if not ev.get("news"):
        missing.append("NEWS_CONTEXT_MISSING")
    if not ev.get("whale"):
        missing.append("WHALE_CONTEXT_MISSING")
    if not ev.get("memory"):
        missing.append("MEMORY_CONTEXT_MISSING")
    if record["subject_type"] == "PAPER_POSITION" and not (ev.get("position_awareness") or ev.get("position_reactions") or ev.get("watchdog_trace")):
        missing.append("POSITION_WATCHDOG_MISSING")
    return missing


def _classify_plan(record: dict[str, Any], ev: dict[str, Any], missing: list[str]) -> tuple[str, str, str]:
    guard = ev.get("same_market_guard") or {}
    risk = ev.get("risk") or {}
    exit_plan = ev.get("exit_plan") or {}
    cap = ev.get("capital_efficiency") or {}
    exit_hold = ev.get("exit_hold") or {}
    coordinator = ev.get("coordinator") or {}
    if guard.get("decision") == "BLOCK":
        return "SAME_MARKET_BLOCKED", "BLOCKED", "BLOCKED"
    if str(risk.get("decision") or "").upper() == "BLOCK" or str(risk.get("risk_status") or "").upper() in {"BLOCKED", "ERROR"}:
        return "RISK_BLOCKED", "BLOCKED", "BLOCKED"
    if str(exit_plan.get("status") or exit_plan.get("plan_status") or "").upper() == "BLOCKED":
        return "EXIT_BLOCKED", "BLOCKED", "BLOCKED"
    if cap.get("recommendation") == "CAPITAL_BLOCK":
        return "CAPITAL_BLOCKED", "BLOCKED", "BLOCKED"
    if not (ev.get("payout") or ev.get("exit_hold") or ev.get("capital_efficiency") or ev.get("risk") or ev.get("coordinator")):
        return "INSUFFICIENT_DATA", "INSUFFICIENT_DATA", "INSUFFICIENT_DATA"
    decision = str(exit_hold.get("decision") or "").upper()
    if decision in {"EXIT_NOW", "PARTIAL_EXIT_REVIEW", "EMERGENCY_EXIT_REVIEW"}:
        return "EXIT_NOW_REVIEW", "WATCH", "EXIT_REVIEW"
    if record["subject_type"] == "PAPER_POSITION" and decision in {"HOLD_REVIEW", "HOLD_TO_RESOLUTION"}:
        status = "COMPLETE" if _has_complete_core(ev, missing) else "WATCH"
        return "HOLD_REVIEW", status, "HOLD_REVIEW"
    if coordinator.get("final_action") == "PAPER_CANDIDATE_REVIEW":
        status = "COMPLETE" if _has_complete_core(ev, missing) else "PARTIAL"
        if record["subject_type"] == "PAPER_INTENT":
            return "REPRICING_CANDIDATE", status, "PAPER_INTENT_READY_CONTEXT"
        return "REPRICING_CANDIDATE", status, "PAPER_CANDIDATE_REVIEW"
    if cap.get("recommendation") == "CAPITAL_SUPPORT":
        status = "COMPLETE" if _has_complete_core(ev, missing) else "PARTIAL"
        decision_class = "PAPER_INTENT_READY_CONTEXT" if record["subject_type"] == "PAPER_INTENT" else "PAPER_CANDIDATE_REVIEW"
        return "CAPITAL_EFFICIENCY_PLAY", status, decision_class
    if ev.get("payout") and not ev.get("risk") and not ev.get("coordinator"):
        return "WATCH_ONLY", "WATCH", "WATCH"
    status = "COMPLETE" if _has_complete_core(ev, missing) else "PARTIAL"
    decision_class = "PAPER_INTENT_READY_CONTEXT" if record["subject_type"] == "PAPER_INTENT" else "WATCH"
    return "WATCH_ONLY", status, decision_class


def _has_complete_core(ev: dict[str, Any], missing: list[str]) -> bool:
    present = set()
    if ev.get("payout"):
        present.add("PAYOUT_ODDS")
    if ev.get("exit_hold"):
        present.add("EXIT_HOLD")
    if ev.get("capital_efficiency"):
        present.add("CAPITAL_EFFICIENCY")
    if ev.get("risk"):
        present.add("RISK")
    if ev.get("exit_plan"):
        present.add("EXIT_FOUNDATION")
    if ev.get("orderbook"):
        present.add("ORDERBOOK_LIQUIDITY")
    if ev.get("coordinator"):
        present.add("COORDINATOR")
    completeness_blockers = {
        "TIME_TO_RESOLUTION_MISSING",
        "RULES_WORDING_MISSING",
        "SAME_MARKET_GUARD_MISSING",
        "NEWS_CONTEXT_MISSING",
        "WHALE_CONTEXT_MISSING",
        "MEMORY_CONTEXT_MISSING",
        "POSITION_WATCHDOG_MISSING",
    }
    return CORE_REQUIRED <= present and not completeness_blockers & set(missing)


def _economic_thesis(ev: dict[str, Any]) -> str:
    p = ev.get("payout")
    if not p:
        return "No source-backed payout/odds evaluation is available; no economic thesis is claimed."
    fair = "fair probability is not source-backed" if p.get("fair_probability") is None else f"fair probability {p.get('fair_probability')}"
    return (
        f"Payout/Odds evaluation {p.get('evaluation_id')} records price {p.get('price')}, implied probability {p.get('implied_probability')}, "
        f"profit_if_win {p.get('profit_if_win')}, max_loss {p.get('max_loss')}, risk_reward {p.get('risk_reward')}; {fair}."
    )


def _entry_thesis(record: dict[str, Any], ev: dict[str, Any]) -> str:
    risk = ev.get("risk") or {}
    guard = ev.get("same_market_guard") or {}
    book = ev.get("orderbook") or {}
    if guard.get("decision") == "BLOCK":
        return f"Entry is blocked by same-market guard reason {guard.get('blocker_reason')}."
    if str(risk.get("decision") or "").upper() == "BLOCK":
        return f"Entry is blocked by risk decision {risk.get('risk_decision_id')}."
    if not book:
        return "Entry context is incomplete because no source-backed orderbook/liquidity snapshot is linked."
    return (
        f"{record['subject_type']} {record['subject_id']} is evaluated with market {record.get('market_id')} side {record.get('side')} "
        f"using orderbook {book.get('orderbook_snapshot_id') or book.get('id')} and risk decision {risk.get('risk_decision_id') or 'missing'}."
    )


def _exit_thesis(ev: dict[str, Any]) -> str:
    eh = ev.get("exit_hold")
    if not eh:
        return "No source-backed exit/hold evaluation is available; exit thesis is incomplete."
    return f"Exit/Hold evaluation {eh.get('evaluation_id')} says {eh.get('decision')} with exit_now_pnl {eh.get('exit_now_pnl')} and reason: {eh.get('reason')}."


def _hold_thesis(ev: dict[str, Any]) -> str:
    eh = ev.get("exit_hold")
    payout = ev.get("payout")
    if not eh and not payout:
        return "No source-backed hold-to-resolution value is available."
    if eh:
        return (
            f"Hold-to-resolution value {eh.get('hold_to_resolution_value')} and profit_if_win {eh.get('hold_to_resolution_profit_if_win')} "
            f"with time_to_resolution_seconds {eh.get('time_to_resolution_seconds')} and rules_risk {eh.get('rules_risk')}."
        )
    return f"Payout/Odds provides hold payout {payout.get('payout_if_win')} and profit_if_win {payout.get('profit_if_win')}; exit/hold comparison is missing."


def _invalidation_rules(ev: dict[str, Any], missing: list[str]) -> list[str]:
    rules = {
        "TOKEN_BOOK_UNAVAILABLE",
        "SPREAD_WIDENS",
        "LIQUIDITY_DROPS",
        "ADVERSE_NEWS",
        "WHALE_REVERSAL",
        "RULES_RISK_INCREASES",
        "SAME_MARKET_CONFLICT",
        "CAPITAL_RECONCILIATION_ISSUE",
    }
    exit_plan = ev.get("exit_plan") or {}
    rules.update(str(item) for item in _list(exit_plan.get("invalidation_rules")))
    if "ORDERBOOK_LIQUIDITY_MISSING" in missing:
        rules.add("ORDERBOOK_SOURCE_MISSING")
    if "SAME_MARKET_GUARD_MISSING" in missing:
        rules.add("SAME_MARKET_GUARD_MUST_RUN_BEFORE_EXECUTION")
    return sorted(rules)


def _monitoring_plan(record: dict[str, Any], ev: dict[str, Any], missing: list[str]) -> list[dict[str, Any]]:
    domains = [
        ("orderbook_watcher", "ORDERBOOK_LIQUIDITY_MISSING" not in missing),
        ("position_watchdog", record["subject_type"] == "PAPER_POSITION"),
        ("news", "NEWS_CONTEXT_MISSING" not in missing),
        ("whale", "WHALE_CONTEXT_MISSING" not in missing),
        ("liquidity", "ORDERBOOK_LIQUIDITY_MISSING" not in missing),
        ("spread", "ORDERBOOK_LIQUIDITY_MISSING" not in missing),
        ("pnl", record["subject_type"] == "PAPER_POSITION"),
        ("time_to_resolution", "TIME_TO_RESOLUTION_MISSING" not in missing),
        ("rules_status", "RULES_WORDING_MISSING" not in missing),
        ("same_market_guard", ev.get("same_market_guard") is not None),
        ("capital_reconciliation", True),
    ]
    return [{"domain": name, "source_backed_now": available, "status": "ACTIVE_INPUT" if available else "MISSING_INPUT"} for name, available in domains]


def _source_refs(ev: dict[str, Any]) -> dict[str, Any]:
    return {
        "payout_odds_evaluation_id": (ev.get("payout") or {}).get("evaluation_id"),
        "exit_hold_evaluation_id": (ev.get("exit_hold") or {}).get("evaluation_id"),
        "capital_efficiency_evaluation_id": (ev.get("capital_efficiency") or {}).get("evaluation_id"),
        "same_market_guard_decision_id": (ev.get("same_market_guard") or {}).get("decision_id"),
        "risk_decision_id": (ev.get("risk") or {}).get("risk_decision_id"),
        "risk_evidence_mesh_evaluation_id": (ev.get("risk_evidence") or {}).get("evaluation_id"),
        "exit_plan_id": (ev.get("exit_plan") or {}).get("exit_plan_id"),
        "capital_brain_evaluation_id": (ev.get("capital_brain") or {}).get("evaluation_id"),
        "mesh_session_id": (ev.get("session") or {}).get("session_id"),
        "mesh_coordinator_decision_id": (ev.get("coordinator") or {}).get("decision_id"),
        "orderbook_snapshot_id": (ev.get("orderbook") or {}).get("orderbook_snapshot_id") or (ev.get("orderbook") or {}).get("id"),
        "rules_source_id": (ev.get("rules") or {}).get("_source_record_id"),
        "news_source_id": (ev.get("news") or {}).get("impact_id") or (ev.get("news") or {}).get("link_id"),
        "whale_source_id": (ev.get("whale") or {}).get("whale_event_id") or (ev.get("whale") or {}).get("id"),
        "memory_source_id": (ev.get("memory") or {}).get("market_id"),
    }


def _sources(record: dict[str, Any], ev: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"source_table": _source_table(record["subject_type"]), "source_record_id": record["subject_id"], "source_type": record["subject_type"], "contribution_summary": "lifecycle subject source"}]
    mapping = [
        ("payout", "payout_odds_evaluations", "evaluation_id", "PAYOUT_ODDS", "economic payout/odds source"),
        ("exit_hold", "exit_hold_evaluations", "evaluation_id", "EXIT_HOLD", "exit now versus hold source"),
        ("capital_efficiency", "capital_efficiency_evaluations", "evaluation_id", "CAPITAL_EFFICIENCY", "capital dollar-time source"),
        ("same_market_guard", "same_market_side_guard_decisions", "decision_id", "SAME_MARKET_GUARD", "same-market exposure guard source"),
        ("risk_evidence", "risk_evidence_mesh_evaluations", "evaluation_id", "RISK_EVIDENCE_MESH", "source-backed risk evidence mesh source"),
        ("risk", "risk_decisions", "risk_decision_id", "RISK", "risk gate source"),
        ("exit_plan", "exit_plans", "exit_plan_id", "EXIT_FOUNDATION", "exit foundation plan source"),
        ("capital_brain", "capital_brain_evaluations", "evaluation_id", "CAPITAL_BRAIN", "capital brain source"),
        ("session", "mesh_sessions", "session_id", "MESH_SESSION", "mesh session source"),
        ("awareness", "mesh_shared_awareness", "awareness_id", "SHARED_AWARENESS", "shared awareness source"),
        ("coordinator", "mesh_coordinator_decisions", "decision_id", "COORDINATOR", "coordinator judgment source"),
        ("orderbook", "orderbook_snapshots", "orderbook_snapshot_id", "ORDERBOOK_LIQUIDITY", "orderbook and liquidity source"),
        ("position_awareness", "position_awareness", "awareness_id", "POSITION_WATCHDOG", "position awareness source"),
        ("watchdog_trace", "open_position_watchdog_traces", "trace_id", "POSITION_WATCHDOG", "open position watchdog source"),
        ("news", "news_impact_scores", "impact_id", "NEWS_AI_CONTEXT", "news impact source"),
        ("whale", "whale_events", "whale_event_id", "WHALE", "whale event source"),
        ("memory", "market_memory_v2", "market_id", "MEMORY", "market memory source"),
    ]
    for key, table, id_key, source_type, summary in mapping:
        item = ev.get(key)
        if not item:
            continue
        record_id = item.get(id_key) or item.get("id") or item.get("market_id")
        if record_id is not None:
            rows.append({"source_table": table, "source_record_id": str(record_id), "source_type": source_type, "contribution_summary": summary})
    rules = ev.get("rules")
    if rules:
        rows.append({"source_table": rules.get("_source_table") or "rules_analysis", "source_record_id": str(rules.get("_source_record_id") or rules.get("id") or rules.get("market_id")), "source_type": "RULES_WORDING", "contribution_summary": "rules and wording risk source"})
    for opinion in ev.get("opinions") or []:
        rows.append({"source_table": "mesh_brain_opinions", "source_record_id": str(opinion.get("opinion_id") or opinion.get("id")), "source_type": "MESH_BRAIN_OPINION", "contribution_summary": f"{opinion.get('brain_name')} opinion"})
    for conflict in ev.get("conflicts") or []:
        rows.append({"source_table": "mesh_conflict_records", "source_record_id": str(conflict.get("conflict_id") or conflict.get("id")), "source_type": "MESH_CONFLICT", "contribution_summary": str(conflict.get("reason") or conflict.get("conflict_type") or "mesh conflict source")})
    for reaction in ev.get("position_reactions") or []:
        rows.append({"source_table": "position_reactions", "source_record_id": str(reaction.get("reaction_id") or reaction.get("id")), "source_type": "POSITION_WATCHDOG", "contribution_summary": str(reaction.get("summary") or "position reaction source")})
    return rows


def _brain_contributions(ev: dict[str, Any], missing: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(brain: str, stance: str, ctype: str, summary: str, refs: dict[str, Any]) -> None:
        rows.append({"brain_name": brain, "stance": stance, "contribution_type": ctype, "contribution_summary": summary, "source_refs_json": refs})

    payout = ev.get("payout")
    if payout:
        add("Payout/Odds", "OBSERVE", "ECONOMIC_CONTEXT", f"Price {payout.get('price')} implies {payout.get('implied_probability')}; risk_reward {payout.get('risk_reward')}.", {"evaluation_id": payout.get("evaluation_id")})
    exit_hold = ev.get("exit_hold")
    if exit_hold:
        add("Exit/Hold", _stance_for_exit_hold(exit_hold.get("decision")), "EXIT_HOLD_CONTEXT", f"Decision {exit_hold.get('decision')}: {exit_hold.get('reason')}", {"evaluation_id": exit_hold.get("evaluation_id")})
    cap = ev.get("capital_efficiency")
    if cap:
        add("Capital Efficiency", _stance_for_capital(cap.get("recommendation")), "CAPITAL_EFFICIENCY_CONTEXT", f"Recommendation {cap.get('recommendation')}; score {cap.get('capital_efficiency_score')}.", {"evaluation_id": cap.get("evaluation_id")})
    guard = ev.get("same_market_guard")
    if guard:
        add("Same-Market Guard", _stance_for_guard(guard.get("decision")), "EXPOSURE_COHERENCE_CONTEXT", f"Decision {guard.get('decision')}; blocker {guard.get('blocker_reason')}.", {"decision_id": guard.get("decision_id")})
    risk = ev.get("risk")
    if risk:
        add("Risk", "BLOCK" if str(risk.get("decision") or "").upper() == "BLOCK" else "SUPPORT", "RISK_CONTEXT", f"Risk decision {risk.get('decision')} status {risk.get('risk_status')}.", {"risk_decision_id": risk.get("risk_decision_id")})
    risk_evidence = ev.get("risk_evidence")
    if risk_evidence:
        add("Risk Evidence Mesh", "BLOCK" if risk_evidence.get("risk_decision") == "RISK_BLOCK" else "REVIEW", "RISK_EVIDENCE_CONTEXT", f"Risk evidence {risk_evidence.get('risk_decision')} via {risk_evidence.get('risk_blocker_subtype')}; edge {risk_evidence.get('edge_source_type')}.", {"evaluation_id": risk_evidence.get("evaluation_id")})
    exit_plan = ev.get("exit_plan")
    if exit_plan:
        add("Exit Foundation", "BLOCK" if str(exit_plan.get("status") or "").upper() == "BLOCKED" else "SUPPORT", "EXIT_PLAN_CONTEXT", f"Exit plan {exit_plan.get('exit_plan_id')} status {exit_plan.get('status')}.", {"exit_plan_id": exit_plan.get("exit_plan_id")})
    capital = ev.get("capital_brain")
    if capital:
        add("Capital Brain", _stance_for_capital(capital.get("decision")), "CAPITAL_CONTEXT", f"Capital decision {capital.get('decision')}: {capital.get('reason')}", {"evaluation_id": capital.get("evaluation_id")})
    book = ev.get("orderbook")
    if book:
        add("Orderbook/Liquidity", "OBSERVE", "LIQUIDITY_CONTEXT", f"Best bid {book.get('best_bid')}, best ask {book.get('best_ask')}, spread {book.get('spread')}.", {"orderbook_snapshot_id": book.get("orderbook_snapshot_id") or book.get("id")})
    if ev.get("position_awareness") or ev.get("position_reactions") or ev.get("watchdog_trace"):
        add("Position Watchdog", "WATCH", "POSITION_CONTEXT", "Position awareness or reaction evidence is available.", {"position_awareness_id": (ev.get("position_awareness") or {}).get("awareness_id")})
    rules = ev.get("rules")
    if rules:
        add("Rules/Wording", "CAUTION" if _decimal_or_none(rules.get("wording_risk")) and _decimal_or_none(rules.get("wording_risk")) >= Decimal("0.5") else "OBSERVE", "RULES_CONTEXT", f"Rules recommendation {rules.get('recommendation') or rules.get('source_verification_status')}.", {"source_record_id": rules.get("_source_record_id")})
    news = ev.get("news")
    if news:
        add("News/AI Context", "OBSERVE", "NEWS_CONTEXT", f"News context strength {news.get('strength')}; direction {news.get('direction')}.", {"source_record_id": news.get("impact_id") or news.get("link_id")})
    whale = ev.get("whale")
    if whale:
        add("Whale", "OBSERVE", "WHALE_CONTEXT", f"Whale event {whale.get('event_direction_class') or whale.get('event_classification')}.", {"source_record_id": whale.get("whale_event_id") or whale.get("id")})
    memory = ev.get("memory")
    if memory:
        add("Memory", "OBSERVE", "MEMORY_CONTEXT", f"Memory status {memory.get('memory_status')} confidence {memory.get('memory_confidence')}.", {"market_id": memory.get("market_id")})
    coordinator = ev.get("coordinator")
    if coordinator:
        add("Coordinator", _stance_for_coordinator(coordinator), "COORDINATOR_CONTEXT", f"Coordinator action {coordinator.get('final_action')}: {coordinator.get('decision_reason')}", {"decision_id": coordinator.get("decision_id")})
    for opinion in ev.get("opinions") or []:
        add(str(opinion.get("brain_name") or opinion.get("brain_type") or "Mesh Brain"), str(opinion.get("stance") or "OBSERVE"), "MESH_BRAIN_OPINION", str(opinion.get("reasoning_summary") or "Mesh brain opinion."), {"opinion_id": opinion.get("opinion_id")})
    if missing:
        add("Lifecycle Completeness", "WATCH", "MISSING_INPUTS", f"Missing inputs: {', '.join(sorted(set(missing))[:8])}.", {"missing_count": len(set(missing))})
    return rows


def _stance_for_exit_hold(decision: Any) -> str:
    value = str(decision or "").upper()
    if value in {"EXIT_NOW", "PARTIAL_EXIT_REVIEW", "EMERGENCY_EXIT_REVIEW"}:
        return "CAUTION"
    if value == "HOLD_TO_RESOLUTION":
        return "SUPPORT"
    if value == "INSUFFICIENT_DATA":
        return "WATCH"
    return "WATCH"


def _stance_for_capital(value: Any) -> str:
    text = str(value or "").upper()
    if "BLOCK" in text:
        return "BLOCK"
    if "SUPPORT" in text:
        return "SUPPORT"
    return "WATCH"


def _stance_for_guard(value: Any) -> str:
    text = str(value or "").upper()
    if text == "BLOCK":
        return "BLOCK"
    if text == "ALLOW":
        return "SUPPORT"
    return "WATCH"


def _stance_for_coordinator(row: dict[str, Any]) -> str:
    action = str(row.get("final_action") or "").upper()
    stance = str(row.get("final_stance") or "").upper()
    if action == "BLOCK" or stance == "BLOCK":
        return "BLOCK"
    if "INSUFFICIENT" in action or "INSUFFICIENT" in stance:
        return "WATCH"
    if action in {"PAPER_CANDIDATE_REVIEW", "PAPER_INTENT_READY_CONTEXT"}:
        return "SUPPORT"
    return "WATCH"


def _upsert_plan(conn: Any, plan: dict[str, Any], sources: list[dict[str, Any]], contributions: list[dict[str, Any]]) -> None:
    params = {
        **plan,
        "invalidation_rules_json": Jsonb(_json_safe(plan["invalidation_rules_json"])),
        "capital_plan_json": Jsonb(_json_safe(plan["capital_plan_json"])),
        "monitoring_plan_json": Jsonb(_json_safe(plan["monitoring_plan_json"])),
        "risk_summary_json": Jsonb(_json_safe(plan["risk_summary_json"])),
        "liquidity_summary_json": Jsonb(_json_safe(plan["liquidity_summary_json"])),
        "payout_summary_json": Jsonb(_json_safe(plan["payout_summary_json"])),
        "exit_hold_summary_json": Jsonb(_json_safe(plan["exit_hold_summary_json"])),
        "capital_efficiency_summary_json": Jsonb(_json_safe(plan["capital_efficiency_summary_json"])),
        "same_market_summary_json": Jsonb(_json_safe(plan["same_market_summary_json"])),
        "coordinator_judgment_json": Jsonb(_json_safe(plan["coordinator_judgment_json"])),
        "missing_inputs_json": Jsonb(_json_safe(plan["missing_inputs_json"])),
        "source_refs_json": Jsonb(_json_safe(plan["source_refs_json"])),
        "metadata_json": Jsonb(_json_safe(plan["metadata_json"])),
    }
    conn.execute(
        """
        INSERT INTO trade_lifecycle_plans (
            plan_id, subject_type, subject_id, market_id, condition_id, side, token_id, mesh_session_id,
            strategy_type, plan_status, decision_class, economic_thesis, entry_thesis, exit_thesis,
            hold_to_resolution_thesis, invalidation_rules_json, capital_plan_json, monitoring_plan_json,
            risk_summary_json, liquidity_summary_json, payout_summary_json, exit_hold_summary_json,
            capital_efficiency_summary_json, same_market_summary_json, coordinator_judgment_json,
            missing_inputs_json, source_refs_json, metadata_json
        ) VALUES (
            %(plan_id)s,%(subject_type)s,%(subject_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,%(mesh_session_id)s,
            %(strategy_type)s,%(plan_status)s,%(decision_class)s,%(economic_thesis)s,%(entry_thesis)s,%(exit_thesis)s,
            %(hold_to_resolution_thesis)s,%(invalidation_rules_json)s,%(capital_plan_json)s,%(monitoring_plan_json)s,
            %(risk_summary_json)s,%(liquidity_summary_json)s,%(payout_summary_json)s,%(exit_hold_summary_json)s,
            %(capital_efficiency_summary_json)s,%(same_market_summary_json)s,%(coordinator_judgment_json)s,
            %(missing_inputs_json)s,%(source_refs_json)s,%(metadata_json)s
        )
        ON CONFLICT (plan_id) DO UPDATE SET
            market_id=EXCLUDED.market_id,
            condition_id=EXCLUDED.condition_id,
            side=EXCLUDED.side,
            token_id=EXCLUDED.token_id,
            mesh_session_id=EXCLUDED.mesh_session_id,
            strategy_type=EXCLUDED.strategy_type,
            plan_status=EXCLUDED.plan_status,
            decision_class=EXCLUDED.decision_class,
            economic_thesis=EXCLUDED.economic_thesis,
            entry_thesis=EXCLUDED.entry_thesis,
            exit_thesis=EXCLUDED.exit_thesis,
            hold_to_resolution_thesis=EXCLUDED.hold_to_resolution_thesis,
            invalidation_rules_json=EXCLUDED.invalidation_rules_json,
            capital_plan_json=EXCLUDED.capital_plan_json,
            monitoring_plan_json=EXCLUDED.monitoring_plan_json,
            risk_summary_json=EXCLUDED.risk_summary_json,
            liquidity_summary_json=EXCLUDED.liquidity_summary_json,
            payout_summary_json=EXCLUDED.payout_summary_json,
            exit_hold_summary_json=EXCLUDED.exit_hold_summary_json,
            capital_efficiency_summary_json=EXCLUDED.capital_efficiency_summary_json,
            same_market_summary_json=EXCLUDED.same_market_summary_json,
            coordinator_judgment_json=EXCLUDED.coordinator_judgment_json,
            missing_inputs_json=EXCLUDED.missing_inputs_json,
            source_refs_json=EXCLUDED.source_refs_json,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=now()
        """,
        params,
    )
    for source in sources:
        conn.execute(
            """
            INSERT INTO trade_lifecycle_plan_sources (plan_id,source_table,source_record_id,source_type,contribution_summary)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (plan["plan_id"], source["source_table"], str(source["source_record_id"]), source["source_type"], source["contribution_summary"]),
        )
    for contribution in contributions:
        conn.execute(
            """
            INSERT INTO trade_lifecycle_brain_contributions (plan_id,brain_name,stance,contribution_type,contribution_summary,source_refs_json)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (plan_id, brain_name, contribution_type) DO UPDATE SET
                stance=EXCLUDED.stance,
                contribution_summary=EXCLUDED.contribution_summary,
                source_refs_json=EXCLUDED.source_refs_json
            """,
            (
                plan["plan_id"],
                contribution["brain_name"],
                contribution["stance"],
                contribution["contribution_type"],
                contribution["contribution_summary"],
                Jsonb(_json_safe(contribution.get("source_refs_json") or {})),
            ),
        )


def _plan_id(record: dict[str, Any], ev: dict[str, Any], strategy_type: str, plan_status: str, decision_class: str) -> str:
    refs = _source_refs(ev)
    raw = "|".join(
        [
            record["subject_type"],
            record["subject_id"],
            strategy_type,
            plan_status,
            decision_class,
            *(str(refs.get(key) or "") for key in sorted(refs)),
        ]
    )
    return f"trade_lifecycle_{uuid5(NAMESPACE_URL, raw).hex}"


def _latest_rows(conn: Any, *, limit: int) -> list[dict[str, Any]]:
    return _fetchall(
        conn,
        """
        SELECT plan_id,subject_type,subject_id,market_id,side,mesh_session_id,strategy_type,plan_status,
               decision_class,missing_inputs_json,created_at
        FROM trade_lifecycle_plans
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        (limit,),
    )


def _related_subject(conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
    table = _source_table(row["subject_type"])
    key = {"PAPER_POSITION": "id::text", "PAPER_INTENT": "paper_intent_id", "PAPER_CANDIDATE": "eligibility_id", "FRESH_SEED": "seed_id"}[row["subject_type"]]
    if not _table_exists(conn, table):
        return None
    return _fetchone(conn, f"SELECT * FROM {table} WHERE {key}=%s", (row["subject_id"],))


def _source_table(subject_type: str) -> str:
    return {"PAPER_POSITION": "paper_positions", "PAPER_INTENT": "paper_intents", "PAPER_CANDIDATE": "paper_eligibility_candidates", "FRESH_SEED": "fresh_candidate_seeds"}[subject_type]


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "trade_lifecycle_plans") and _table_exists(conn, "trade_lifecycle_plan_sources") and _table_exists(conn, "trade_lifecycle_brain_contributions")


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        "total_plans": 0,
        "latest_plans": [],
        "top_missing_inputs": [],
    }


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {table: _count_table(conn, table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")}
    account = _fetchone(conn, "SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'") if _table_exists(conn, "paper_accounts") else None
    counts["capital_balances"] = _json_safe(account) if account else None
    return counts


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: Any) -> int:
    return int(value or 0)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
