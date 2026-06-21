from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.full_mesh_contract import mesh_response
from app.services.full_mesh_registry import full_mesh_registry
from app.services.source_backed_edge_engine import build_edge_thesis, risk_mapping_from_thesis
from app.services.source_organ_runtime import SOURCE_ORGAN_NAMES, query_source_organ_with_connection


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"

SUBJECT_TYPES = {"FRESH_SEED", "PAPER_CANDIDATE", "PAPER_INTENT", "PAPER_POSITION", "LIFECYCLE_PLAN"}
MAX_SPREAD = Decimal("0.08")
MIN_LIQUIDITY_SCORE = Decimal("0.25")
ORDERBOOK_TTL_SECONDS = 180

OPTIONAL_CONTEXT = {
    "WHALE_CONTEXT_MISSING",
    "MEMORY_CONTEXT_MISSING",
    "SOCIAL_CONTEXT_MISSING",
    "FAIR_PROBABILITY_MISSING",
    "NEWS_CONTEXT_MISSING",
    "AI_CONTEXT_MISSING",
    "SOURCE_RELIABILITY_MISSING",
}

CRITICAL_LINEAGE = {"MARKET_ID", "SIDE", "TOKEN_ID", "ACTIVE_FRESH_TRUSTED_ORDERBOOK", "EXECUTABLE_PRICE"}


class RiskEvidenceMeshService:
    """Source-backed risk/edge evidence mesh.

    This service produces derived reasoning records only. It cannot create
    intents, orders, fills, positions, closes, or capital ledger rows.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def evaluate_recent(self, *, limit: int = 100, subject_type: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "evaluations_created": 0}
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return _empty("MISSING_TABLES", generated_at)
            before = _count_table(conn, "risk_evidence_mesh_evaluations")
            safety_before = _safety_counts(conn)
            records = _records(conn, subject_type=subject, limit=limit)
            outcomes = [self.evaluate_record_with_conn(conn, record, dry_run=dry_run) for record in records]
            after = _count_table(conn, "risk_evidence_mesh_evaluations")
            safety_after = _safety_counts(conn)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "evaluations_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_risk_decision": dict(Counter(item["risk_decision"] for item in outcomes)),
                "outcomes_by_blocker_subtype": dict(Counter(item["risk_blocker_subtype"] for item in outcomes)),
                "edge_source_type_counts": dict(Counter(item["edge_source_type"] for item in outcomes)),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": safety_before != safety_after,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
            }
        )

    def evaluate_subject_with_conn(self, conn: Any, *, subject_type: str, subject_id: str, dry_run: bool = False) -> dict[str, Any]:
        subject = str(subject_type).upper()
        record = _record_by_subject(conn, subject_type=subject, subject_id=str(subject_id))
        if record is None:
            return {"mock_data": False, "status": "SUBJECT_NOT_FOUND", "subject_type": subject, "subject_id": str(subject_id)}
        return self.evaluate_record_with_conn(conn, record, dry_run=dry_run)

    def evaluate_record_with_conn(self, conn: Any, record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        evidence = _collect_evidence(conn, record)
        classified = _classify(record, evidence)
        evaluation = {
            "evaluation_id": _evaluation_id(record, evidence, classified),
            "subject_type": record["subject_type"],
            "subject_id": record["subject_id"],
            "market_id": record.get("market_id"),
            "condition_id": record.get("condition_id"),
            "side": record.get("side"),
            "token_id": record.get("token_id"),
            **classified,
            "source_refs_json": _source_refs(evidence),
            "metadata_json": {
                "derived_truth_only": True,
                "no_trading_mutation": True,
                "no_fake_edge": True,
                "no_fake_probability": True,
                "source_refresh_cycle_id": classified.get("edge_thesis", {}).get("source_refresh_cycle_id"),
                "propagation_context": {
                    **(classified.get("edge_thesis", {}).get("propagation_context") or {}),
                    "edge_thesis_id": classified.get("edge_thesis", {}).get("edge_thesis_id"),
                },
                "lineage_classification": _lineage_classification(classified),
                "edge_thesis": classified.get("edge_thesis"),
            },
        }
        sources = _sources(conn, record, evidence)
        if not dry_run:
            _upsert_evaluation(conn, evaluation, sources)
        return _json_safe(
            {
                "evaluation_id": evaluation["evaluation_id"],
                "subject_type": record["subject_type"],
                "subject_id": record["subject_id"],
                "market_id": record.get("market_id"),
                "side": record.get("side"),
                "risk_decision": classified["risk_decision"],
                "risk_blocker_subtype": classified["risk_blocker_subtype"],
                "edge_source_type": classified["edge_source_type"],
                "edge_status": classified["edge_status"],
                "critical_missing": classified["critical_evidence_missing_json"],
                "optional_missing": classified["optional_context_missing_json"],
                "blocking_evidence": classified["blocking_evidence_json"],
                "dry_run": dry_run,
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
            return None
        return _fetchone(
            conn,
            """
            SELECT * FROM risk_evidence_mesh_evaluations
            WHERE subject_type=%s AND subject_id=%s
            ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT 1
            """,
            (str(subject_type).upper(), str(subject_id)),
        )

    def latest_for_plan(self, conn: Any, plan: dict[str, Any]) -> dict[str, Any] | None:
        row = self.latest_for_subject(conn, subject_type="LIFECYCLE_PLAN", subject_id=str(plan.get("plan_id") or ""))
        if row:
            return row
        return self.latest_for_subject(conn, subject_type=str(plan.get("subject_type") or ""), subject_id=str(plan.get("subject_id") or ""))

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
                return _empty("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE risk_decision='RISK_SUPPORT') AS support_count,
                  COUNT(*) FILTER (WHERE risk_decision='RISK_WATCH') AS watch_count,
                  COUNT(*) FILTER (WHERE risk_decision='RISK_REVIEW') AS review_count,
                  COUNT(*) FILTER (WHERE risk_decision='RISK_BLOCK') AS block_count,
                  COALESCE(AVG(evidence_quality_score),0) AS avg_score
                FROM risk_evidence_mesh_evaluations
                """,
            ) or {}
            by_decision = _fetchall(conn, "SELECT risk_decision, COUNT(*) AS count FROM risk_evidence_mesh_evaluations GROUP BY risk_decision ORDER BY risk_decision")
            by_blocker = _fetchall(conn, "SELECT risk_blocker_subtype, COUNT(*) AS count FROM risk_evidence_mesh_evaluations GROUP BY risk_blocker_subtype ORDER BY count DESC,risk_blocker_subtype LIMIT %s", (limit,))
            by_edge = _fetchall(conn, "SELECT edge_source_type, COUNT(*) AS count FROM risk_evidence_mesh_evaluations GROUP BY edge_source_type ORDER BY count DESC,edge_source_type")
            optional = _jsonb_item_counts(conn, "optional_context_missing_json", limit)
            critical = _jsonb_item_counts(conn, "critical_evidence_missing_json", limit)
            latest = _fetchall(conn, "SELECT * FROM risk_evidence_mesh_evaluations ORDER BY created_at DESC,id DESC LIMIT %s", (limit,))
            closest = _fetchall(
                conn,
                """
                SELECT *
                FROM risk_evidence_mesh_evaluations
                WHERE risk_decision IN ('RISK_WATCH','RISK_REVIEW','RISK_SUPPORT')
                ORDER BY evidence_quality_score DESC, created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            governance_trace = _governance_trace_summary(conn, limit=limit)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_evaluations": _int(totals.get("total")),
                "RISK_SUPPORT": _int(totals.get("support_count")),
                "RISK_WATCH": _int(totals.get("watch_count")),
                "RISK_REVIEW": _int(totals.get("review_count")),
                "RISK_BLOCK": _int(totals.get("block_count")),
                "avg_evidence_quality_score": _float(totals.get("avg_score")),
                "decisions_by_type": {str(row["risk_decision"]): _int(row["count"]) for row in by_decision},
                "blocker_subtypes": {str(row["risk_blocker_subtype"]): _int(row["count"]) for row in by_blocker},
                "edge_source_type_counts": {str(row["edge_source_type"]): _int(row["count"]) for row in by_edge},
                "optional_missing_counts": optional,
                "critical_missing_counts": critical,
                **governance_trace,
                "closest_to_actionable_risk_subjects": closest,
                "latest_evaluations": latest,
            }
        )

    def detail(self, evaluation_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluation_id": evaluation_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "risk_evidence_mesh_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluation_id": evaluation_id}
            row = _fetchone(conn, "SELECT * FROM risk_evidence_mesh_evaluations WHERE evaluation_id=%s", (evaluation_id,))
            if not row:
                return {"mock_data": False, "status": "NOT_FOUND", "evaluation_id": evaluation_id}
            sources = _fetchall(conn, "SELECT * FROM risk_evidence_mesh_sources WHERE evaluation_id=%s ORDER BY linked_at,id", (evaluation_id,))
        return _json_safe({"mock_data": False, "status": "OK", "generated_at": datetime.now(UTC).isoformat(), "evaluation": row, "sources": sources})


def _records(conn: Any, *, subject_type: str | None, limit: int) -> list[dict[str, Any]]:
    wanted = [subject_type] if subject_type else ["LIFECYCLE_PLAN", "PAPER_INTENT", "PAPER_CANDIDATE", "FRESH_SEED"]
    rows: list[dict[str, Any]] = []
    if "LIFECYCLE_PLAN" in wanted:
        rows.extend(_lifecycle_plan_records(conn, limit=limit))
    if "PAPER_INTENT" in wanted:
        rows.extend(_intent_records(conn, limit=limit))
    if "PAPER_CANDIDATE" in wanted:
        rows.extend(_candidate_records(conn, limit=limit))
    if "FRESH_SEED" in wanted:
        rows.extend(_fresh_seed_records(conn, limit=limit))
    if "PAPER_POSITION" in wanted:
        rows.extend(_position_records(conn, limit=limit))
    return rows[: max(0, limit * max(1, len(wanted)))]


def _record_by_subject(conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    if subject_type == "LIFECYCLE_PLAN":
        rows = _lifecycle_plan_records(conn, limit=1, subject_id=subject_id)
    elif subject_type == "PAPER_INTENT":
        rows = _intent_records(conn, limit=1, subject_id=subject_id)
    elif subject_type == "PAPER_CANDIDATE":
        rows = _candidate_records(conn, limit=1, subject_id=subject_id)
    elif subject_type == "PAPER_POSITION":
        rows = _position_records(conn, limit=1, subject_id=subject_id)
    else:
        rows = _fresh_seed_records(conn, limit=1, subject_id=subject_id)
    return rows[0] if rows else None


def _lifecycle_plan_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "trade_lifecycle_plans"):
        return []
    where = "WHERE plan_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(conn, f"SELECT * FROM trade_lifecycle_plans {where} ORDER BY created_at DESC,id DESC LIMIT %s", tuple(params))
    records = []
    for row in rows:
        refs = _dict(row.get("source_refs_json"))
        records.append(
            {
                "subject_type": "LIFECYCLE_PLAN",
                "subject_id": row["plan_id"],
                "plan": row,
                "market_id": row.get("market_id"),
                "condition_id": row.get("condition_id"),
                "side": row.get("side"),
                "token_id": row.get("token_id"),
                "source_refs_json": refs,
                "risk_decision_id": refs.get("risk_decision_id") or _dict(row.get("risk_summary_json")).get("risk_decision_id"),
                "orderbook_snapshot_id": refs.get("orderbook_snapshot_id") or _dict(row.get("liquidity_summary_json")).get("orderbook_snapshot_id"),
            }
        )
    return records


def _intent_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    where = "WHERE paper_intent_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'PAPER_INTENT' AS subject_type, paper_intent_id AS subject_id, market_id, side,
               NULL::text AS condition_id, NULL::text AS token_id, intended_price AS entry_price,
               risk_decision_id, exit_plan_id, orderbook_snapshot_id::text, evidence AS payload_json, created_at, updated_at
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
    return _fetchall(
        conn,
        f"""
        SELECT 'PAPER_CANDIDATE' AS subject_type,
               pec.eligibility_id AS subject_id,
               pec.market_id,
               pec.side,
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
               NULL::numeric AS entry_price,
               pec.risk_decision_id,
               pec.exit_plan_id,
               COALESCE(obs.id::text, pec.orderbook_snapshot_id::text) AS orderbook_snapshot_id,
               pec.evidence AS payload_json,
               pec.created_at,
               pec.updated_at
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
        {where}
        ORDER BY pec.updated_at DESC, pec.id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _fresh_seed_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fresh_candidate_seeds"):
        return []
    where = "WHERE seed_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'FRESH_SEED' AS subject_type, seed_id AS subject_id, market_id, side, condition_id,
               expected_token_id AS token_id, NULL::numeric AS entry_price, NULL::text AS risk_decision_id,
               NULL::text AS exit_plan_id, NULL::text AS orderbook_snapshot_id, metadata_json AS payload_json,
               created_at, created_at AS updated_at
        FROM fresh_candidate_seeds
        {where}
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _position_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    where = "WHERE id::text=%s" if subject_id else "WHERE current_status IN ('OPEN','EXIT_PENDING') AND closed_at IS NULL AND COALESCE(excluded_from_active_paper_truth,false)=false"
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(
        conn,
        f"""
        SELECT 'PAPER_POSITION' AS subject_type, id::text AS subject_id, market_id, intended_outcome AS side,
               NULL::text AS condition_id, NULL::text AS token_id, avg_entry AS entry_price,
               payload_json->>'risk_decision_id' AS risk_decision_id, payload_json->>'exit_plan_id' AS exit_plan_id,
               NULLIF(payload_json->>'orderbook_snapshot_id','') AS orderbook_snapshot_id, payload_json,
               opened_at AS created_at, opened_at AS updated_at
        FROM paper_positions
        {where}
        ORDER BY opened_at DESC NULLS LAST,id DESC
        LIMIT %s
        """,
        tuple(params),
    )


def _collect_evidence(conn: Any, record: dict[str, Any]) -> dict[str, Any]:
    market_id = _text(record.get("market_id"))
    subject_type = record["subject_type"]
    subject_id = record["subject_id"]
    plan = _dict(record.get("plan"))
    refs = _dict(record.get("source_refs_json")) or _dict(plan.get("source_refs_json"))
    risk = _latest_risk(conn, record, market_id=market_id, refs=refs)
    book = _latest_orderbook(conn, record, market_id=market_id, refs=refs)
    payout = _latest_subject_row(conn, "payout_odds_evaluations", "evaluation_id", subject_type, subject_id, refs.get("payout_odds_evaluation_id"))
    exit_hold = _latest_subject_row(conn, "exit_hold_evaluations", "evaluation_id", subject_type, subject_id, refs.get("exit_hold_evaluation_id"))
    capital_efficiency = _latest_subject_row(conn, "capital_efficiency_evaluations", "evaluation_id", subject_type, subject_id, refs.get("capital_efficiency_evaluation_id"))
    guard = _latest_guard(conn, record, refs=refs)
    lifecycle_governance = _latest_governance(conn, record, refs=refs)
    identity = {
        "candidate_id": subject_id if subject_type == "PAPER_CANDIDATE" else record.get("candidate_id"),
        "market_id": market_id,
        "condition_id": _text(record.get("condition_id")),
        "side": _text(record.get("side")),
        "token_id": _text(record.get("token_id")),
        "correlation_id": _text(record.get("correlation_id")),
        "event_id": _text(record.get("event_id")),
    }
    mesh_responses = _source_organ_mesh_responses(conn, identity)
    source_refresh_context = _latest_source_refresh_context(conn)
    return {
        "plan": plan,
        "risk": risk,
        "orderbook": book,
        "payout": payout,
        "exit_hold": exit_hold,
        "capital_efficiency": capital_efficiency,
        "same_market_guard": guard,
        "lifecycle_governance": lifecycle_governance,
        "news": _latest_market_row(conn, "news_impact_scores", market_id),
        "whale": _latest_market_row(conn, "whale_events", market_id),
        "social": _latest_market_row(conn, "social_market_links", market_id),
        "market_movement": _latest_market_row(conn, "market_technical_signals", market_id, time_col="ts"),
        "memory": _latest_market_row(conn, "market_memory_v2", market_id, time_col="updated_at"),
        "neuron_signals": _latest_neuron_signals(conn, market_id),
        "mesh_responses": mesh_responses,
        "source_refresh_context": source_refresh_context,
    }


def _source_organ_mesh_responses(conn: Any, identity: dict[str, Any]) -> list[dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    for registration in full_mesh_registry():
        if registration.neuron_name not in SOURCE_ORGAN_NAMES:
            continue
        try:
            with conn.transaction():
                responses.append(query_source_organ_with_connection(registration, identity=identity, conn=conn))
        except Exception as exc:
            responses.append(
                mesh_response(
                    neuron_name=registration.neuron_name,
                    neuron_type=registration.neuron_type,
                    identity=identity,
                    response_state="ERROR",
                    supports_side="UNKNOWN",
                    confidence=0.0,
                    strength=0.0,
                    source_backed=False,
                    summary=f"{registration.neuron_name} source organ lookup failed.",
                    reason=f"{type(exc).__name__}: {exc}",
                    blocker_code=f"{registration.neuron_name.upper()}_UNAVAILABLE_ERROR",
                    required_to_pass=[f"Fix {registration.neuron_name} source organ runtime lookup."],
                    metadata={"source_organ": True, "source_organ_runtime_state": "UNAVAILABLE_ERROR", "organ_name": registration.neuron_name, "error_type": type(exc).__name__},
                )
            )
    return responses


def _classify(record: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    present: set[str] = set()
    missing: set[str] = set()
    optional_missing: set[str] = set()
    blocking: set[str] = set()
    supporting: set[str] = set()

    market_id = _text(record.get("market_id"))
    side = _text(record.get("side"))
    token_id = _text(record.get("token_id"))
    condition_id = _text(record.get("condition_id"))
    if market_id:
        present.add("MARKET_ID")
    else:
        missing.add("MARKET_ID_MISSING")
    if side:
        present.add("SIDE")
    else:
        missing.add("SIDE_MISSING")
    if condition_id:
        present.add("CONDITION_ID")
    else:
        missing.add("CONDITION_ID_MISSING")
    if token_id:
        present.add("TOKEN_ID")
    else:
        missing.add("TOKEN_MISSING")

    book = ev.get("orderbook") or {}
    book_status = str(book.get("snapshot_status") or "").upper()
    book_age = _age_seconds(book.get("collected_at") or book.get("snapshot_at") or book.get("created_at"))
    if not book:
        missing.add("TRUSTED_ORDERBOOK_MISSING")
        blocking.add("RISK_BLOCKED_NO_TRUSTED_ORDERBOOK")
    elif bool(book.get("is_stale")) or book_status in {"STALE", "ERROR", "EMPTY", "PARTIAL"} or (book_age is not None and book_age > ORDERBOOK_TTL_SECONDS):
        missing.add("TRUSTED_ORDERBOOK_STALE")
        blocking.add("RISK_BLOCKED_STALE_CRITICAL_SOURCE")
    else:
        present.add("ACTIVE_FRESH_TRUSTED_ORDERBOOK")
        supporting.add("ORDERBOOK_LIQUIDITY_SETUP")
    executable_price = _decimal_or_none(book.get("best_ask") or record.get("entry_price"))
    if executable_price is None:
        missing.add("EXECUTABLE_PRICE_MISSING")
        blocking.add("RISK_BLOCKED_MISSING_EXECUTABLE_PRICE")
    else:
        present.add("EXECUTABLE_PRICE")
    spread = _decimal_or_none(book.get("spread"))
    if spread is not None:
        present.add("SPREAD")
        if spread > MAX_SPREAD:
            blocking.add("RISK_BLOCKED_SPREAD")
    liquidity = _decimal_or_none(book.get("liquidity_score"))
    if liquidity is not None:
        present.add("LIQUIDITY_SCORE")
        if liquidity < MIN_LIQUIDITY_SCORE:
            blocking.add("RISK_BLOCKED_BAD_LIQUIDITY")

    payout = ev.get("payout") or {}
    if payout:
        supporting.add("PAYOUT_ODDS")
        if payout.get("fair_probability") is None:
            optional_missing.add("FAIR_PROBABILITY_MISSING")
    else:
        optional_missing.add("PAYOUT_ODDS_MISSING")
    if ev.get("exit_hold"):
        supporting.add("EXIT_HOLD")
    if ev.get("capital_efficiency"):
        supporting.add("CAPITAL_EFFICIENCY")
    if ev.get("lifecycle_governance"):
        supporting.add("LIFECYCLE_GOVERNANCE")
    if ev.get("news"):
        supporting.add("NEWS_CONTEXT")
    else:
        optional_missing.add("NEWS_CONTEXT_MISSING")
    if ev.get("whale"):
        supporting.add("WHALE_CONTEXT")
    else:
        optional_missing.add("WHALE_CONTEXT_MISSING")
    if ev.get("social"):
        supporting.add("SOCIAL_CONTEXT")
    else:
        optional_missing.add("SOCIAL_CONTEXT_MISSING")
    if ev.get("market_movement"):
        supporting.add("MARKET_MOVEMENT_CONTEXT")
    if ev.get("memory"):
        supporting.add("MEMORY_CONTEXT")
    else:
        optional_missing.add("MEMORY_CONTEXT_MISSING")

    guard = ev.get("same_market_guard") or {}
    if str(guard.get("decision") or "").upper() == "BLOCK":
        blocking.add("RISK_BLOCKED_SAME_MARKET_CONFLICT")
    cap = ev.get("capital_efficiency") or {}
    if str(cap.get("recommendation") or "").upper() == "CAPITAL_BLOCK":
        blocking.add("RISK_BLOCKED_CAPITAL")

    risk = ev.get("risk") or {}
    risk_blockers = {str(item).upper() for item in _list(risk.get("blockers"))}
    partial_lineage = bool(risk_blockers & {"MISSING_MARKET_LINK", "MISSING_SIGNAL_MARKET_BINDING", "WEAK_LINEAGE_OR_PROVENANCE"})
    critical_lineage_missing = bool(CRITICAL_LINEAGE - present)
    if critical_lineage_missing:
        blocking.add("RISK_BLOCKED_LINEAGE_CRITICAL")
    if partial_lineage and not critical_lineage_missing:
        supporting.add("PARTIAL_LINEAGE_PROVENANCE")

    edge_thesis = build_edge_thesis(record, ev)
    source_refresh_context = ev.get("source_refresh_context") or {}
    if source_refresh_context:
        propagation_context = dict(edge_thesis.get("propagation_context") or {})
        propagation_context.update(
            {
                "source_refresh_cycle_id": source_refresh_context.get("source_refresh_cycle_id"),
                "source_refresh_completed_at": source_refresh_context.get("source_refresh_completed_at"),
                "candidate_id": record["subject_id"] if record["subject_type"] == "PAPER_CANDIDATE" else record.get("candidate_id"),
                "market_id": record.get("market_id"),
                "condition_id": record.get("condition_id"),
                "side": record.get("side"),
                "token_id": record.get("token_id"),
            }
        )
        edge_thesis["source_refresh_cycle_id"] = source_refresh_context.get("source_refresh_cycle_id")
        edge_thesis["propagation_context"] = propagation_context
    edge_source_type, edge_status = risk_mapping_from_thesis(edge_thesis)
    edge_state = str(edge_thesis.get("edge_state") or "")
    if edge_state == "SOURCE_CONFLICT":
        blocking.add("RISK_BLOCKED_SOURCE_CONFLICT")
    elif edge_state == "EDGE_STALE":
        blocking.add("RISK_BLOCKED_EDGE_STALE")
    if not blocking and edge_status == "NO_CURRENT_DIRECTIONAL_EDGE":
        blocking.add("RISK_BLOCKED_NO_CURRENT_DIRECTIONAL_EDGE")
    if not blocking and edge_status == "NO_SOURCE_BACKED_EDGE":
        blocking.add("RISK_BLOCKED_NO_SOURCE_BACKED_EDGE")

    if blocking:
        risk_decision = "RISK_BLOCK"
        subtype = _primary_blocker(blocking)
    elif "PARTIAL_LINEAGE_PROVENANCE" in supporting:
        risk_decision = "RISK_REVIEW"
        subtype = "RISK_REVIEW_LINEAGE_PARTIAL"
    elif edge_status == "SOURCE_BACKED_EDGE_PRESENT":
        risk_decision = "RISK_REVIEW" if optional_missing else "RISK_SUPPORT"
        subtype = "RISK_REVIEW_EDGE_WEAK" if risk_decision == "RISK_REVIEW" else "RISK_SUPPORT_SOURCE_BACKED_EDGE"
    elif edge_status == "EDGE_WEAK":
        risk_decision = "RISK_REVIEW"
        subtype = "RISK_REVIEW_EDGE_WEAK"
    else:
        risk_decision = "RISK_WATCH"
        subtype = "RISK_WATCH_OPTIONAL_CONTEXT_MISSING"

    if risk_decision in {"RISK_WATCH", "RISK_REVIEW"} and optional_missing:
        supporting.add("OPTIONAL_CONTEXT_MISSING_NON_BLOCKING")

    score = _score(present, supporting, missing, blocking, optional_missing)
    return {
        "critical_evidence_present_json": sorted(present),
        "critical_evidence_missing_json": sorted(missing),
        "supporting_evidence_present_json": sorted(supporting),
        "optional_context_missing_json": sorted(optional_missing),
        "blocking_evidence_json": sorted(blocking),
        "evidence_quality_score": score,
        "edge_source_type": edge_source_type,
        "edge_status": edge_status,
        "risk_decision": risk_decision,
        "risk_blocker_subtype": subtype,
        "reason": _reason(risk_decision, subtype, edge_source_type, missing, optional_missing, blocking),
        "edge_thesis": edge_thesis,
    }


def _edge(
    ev: dict[str, Any],
    book: dict[str, Any],
    payout: dict[str, Any],
    cap: dict[str, Any],
    supporting: set[str],
    blocking: set[str],
) -> tuple[str, str]:
    if blocking:
        return "UNKNOWN", "EDGE_NOT_EVALUATED"
    risk_reward = _decimal_or_none(payout.get("risk_reward"))
    cap_rec = str(cap.get("recommendation") or "").upper()
    cap_score = _decimal_or_none(cap.get("capital_efficiency_score"))
    if risk_reward is not None and risk_reward >= Decimal("1.0") and "ORDERBOOK_LIQUIDITY_SETUP" in supporting:
        if cap_rec in {"CAPITAL_SUPPORT", "CAPITAL_WATCH", "CAPITAL_REDUCE_REVIEW", ""}:
            return ("CAPITAL_EFFICIENCY_SETUP" if cap_score is not None and cap_score >= Decimal("0.4") else "PRICE_PAYOUT_ASYMMETRY", "SOURCE_BACKED_EDGE_PRESENT")
        return "PRICE_PAYOUT_ASYMMETRY", "EDGE_WEAK"
    if ev.get("news") and book:
        return "NEWS_REPRICING_SIGNAL", "EDGE_WEAK"
    if "ORDERBOOK_LIQUIDITY_SETUP" in supporting and (risk_reward is not None or cap_score is not None):
        return "ORDERBOOK_LIQUIDITY_SETUP", "EDGE_WEAK"
    return "NO_SOURCE_BACKED_EDGE", "NO_SOURCE_BACKED_EDGE"


def _primary_blocker(blocking: set[str]) -> str:
    order = [
        "RISK_BLOCKED_STALE_CRITICAL_SOURCE",
        "RISK_BLOCKED_NO_TRUSTED_ORDERBOOK",
        "RISK_BLOCKED_MISSING_EXECUTABLE_PRICE",
        "RISK_BLOCKED_SPREAD",
        "RISK_BLOCKED_BAD_LIQUIDITY",
        "RISK_BLOCKED_LINEAGE_CRITICAL",
        "RISK_BLOCKED_SOURCE_CONFLICT",
        "RISK_BLOCKED_EDGE_STALE",
        "RISK_BLOCKED_SAME_MARKET_CONFLICT",
        "RISK_BLOCKED_CAPITAL",
        "RISK_BLOCKED_NO_CURRENT_DIRECTIONAL_EDGE",
        "RISK_BLOCKED_NO_SOURCE_BACKED_EDGE",
    ]
    for item in order:
        if item in blocking:
            return item
    return sorted(blocking)[0] if blocking else "RISK_BLOCKED_UNKNOWN"


def _reason(
    risk_decision: str,
    subtype: str,
    edge_source_type: str,
    missing: set[str],
    optional_missing: set[str],
    blocking: set[str],
) -> str:
    if risk_decision == "RISK_BLOCK":
        return f"Risk Evidence Mesh blocked because {subtype}; blocking evidence: {', '.join(sorted(blocking))}."
    if risk_decision == "RISK_SUPPORT":
        return f"Risk Evidence Mesh supports source-backed edge {edge_source_type}; critical evidence is present."
    if risk_decision == "RISK_REVIEW":
        return f"Risk Evidence Mesh sends to review via {subtype}; optional missing: {', '.join(sorted(optional_missing)) or 'none'}."
    return f"Risk Evidence Mesh watches; missing critical/context: {', '.join(sorted(missing)) or 'none'}; optional missing: {', '.join(sorted(optional_missing)) or 'none'}."


def _latest_risk(conn: Any, record: dict[str, Any], *, market_id: str | None, refs: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "risk_decisions"):
        return None
    risk_id = _text(record.get("risk_decision_id") or refs.get("risk_decision_id"))
    if risk_id:
        row = _fetchone(conn, "SELECT * FROM risk_decisions WHERE risk_decision_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (risk_id,))
        if row:
            return row
    plan = _dict(record.get("plan"))
    summary = _dict(plan.get("risk_summary_json"))
    risk_id = _text(summary.get("risk_decision_id"))
    if risk_id:
        row = _fetchone(conn, "SELECT * FROM risk_decisions WHERE risk_decision_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (risk_id,))
        if row:
            return row
    if market_id:
        return _fetchone(conn, "SELECT * FROM risk_decisions WHERE market_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (market_id,))
    return None


def _latest_orderbook(conn: Any, record: dict[str, Any], *, market_id: str | None, refs: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "orderbook_snapshots"):
        return None
    snapshot_id = _text(record.get("orderbook_snapshot_id") or refs.get("orderbook_snapshot_id"))
    if snapshot_id:
        row = _fetchone(conn, "SELECT * FROM orderbook_snapshots WHERE id::text=%s OR orderbook_snapshot_id=%s ORDER BY collected_at DESC,created_at DESC,id DESC LIMIT 1", (snapshot_id, snapshot_id))
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


def _latest_subject_row(conn: Any, table: str, id_col: str, subject_type: str, subject_id: str, explicit_id: Any) -> dict[str, Any] | None:
    if not _table_exists(conn, table):
        return None
    rows: list[dict[str, Any]] = []
    if explicit_id:
        row = _fetchone(conn, f"SELECT * FROM {table} WHERE {id_col}=%s ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT 1", (str(explicit_id),))
        if row:
            rows.append(row)
    subject_row = _fetchone(conn, f"SELECT * FROM {table} WHERE subject_type=%s AND subject_id=%s ORDER BY updated_at DESC NULLS LAST, created_at DESC,id DESC LIMIT 1", (subject_type, subject_id))
    if subject_row:
        rows.append(subject_row)
    if not rows:
        return None
    return max(rows, key=lambda row: _sort_time(row.get("updated_at") or row.get("created_at")))


def _latest_guard(conn: Any, record: dict[str, Any], *, refs: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "same_market_side_guard_decisions"):
        return None
    guard_id = _text(refs.get("same_market_guard_decision_id"))
    if guard_id:
        row = _fetchone(conn, "SELECT * FROM same_market_side_guard_decisions WHERE decision_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (guard_id,))
        if row:
            return row
    clauses: list[str] = []
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


def _latest_governance(conn: Any, record: dict[str, Any], *, refs: dict[str, Any]) -> dict[str, Any] | None:
    if not _table_exists(conn, "lifecycle_governance_decisions"):
        return None
    plan_id = _text(refs.get("lifecycle_plan_id") or (record.get("plan") or {}).get("plan_id"))
    if plan_id:
        row = _fetchone(conn, "SELECT * FROM lifecycle_governance_decisions WHERE lifecycle_plan_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (plan_id,))
        if row:
            return row
    return _fetchone(conn, "SELECT * FROM lifecycle_governance_decisions WHERE subject_type=%s AND subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (record["subject_type"], record["subject_id"]))


def _latest_source_refresh_context(conn: Any) -> dict[str, Any]:
    if not _table_exists(conn, "source_refresh_cycles"):
        return {}
    row = _fetchone(
        conn,
        """
        SELECT cycle_id, completed_at, orchestrator_state, sources_checked, sources_refreshed,
               sources_failed, sources_no_new_data, derived_signals_created
        FROM source_refresh_cycles
        ORDER BY completed_at DESC NULLS LAST,id DESC
        LIMIT 1
        """,
    )
    if not row:
        return {}
    return {
        "source_refresh_cycle_id": row.get("cycle_id"),
        "source_refresh_completed_at": row.get("completed_at"),
        "source_refresh_orchestrator_state": row.get("orchestrator_state"),
        "sources_checked": row.get("sources_checked"),
        "sources_refreshed": row.get("sources_refreshed"),
        "sources_failed": row.get("sources_failed"),
        "sources_no_new_data": row.get("sources_no_new_data"),
        "derived_signals_created": row.get("derived_signals_created"),
    }


def _latest_market_row(conn: Any, table: str, market_id: str | None, *, time_col: str = "created_at") -> dict[str, Any] | None:
    if not market_id or not _table_exists(conn, table):
        return None
    return _fetchone(conn, f"SELECT * FROM {table} WHERE market_id=%s ORDER BY {time_col} DESC,id DESC LIMIT 1", (market_id,))


def _latest_neuron_signals(conn: Any, market_id: str | None, *, limit: int = 10) -> list[dict[str, Any]]:
    if not market_id or not _table_exists(conn, "neuron_signals"):
        return []
    return _fetchall(
        conn,
        """
        SELECT *
        FROM neuron_signals
        WHERE market_id=%s
          AND status IN ('ACTIVE','PARTIAL')
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        (market_id, limit),
    )


def _source_refs(ev: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk_decision_id": (ev.get("risk") or {}).get("risk_decision_id"),
        "orderbook_snapshot_id": (ev.get("orderbook") or {}).get("orderbook_snapshot_id") or (ev.get("orderbook") or {}).get("id"),
        "payout_odds_evaluation_id": (ev.get("payout") or {}).get("evaluation_id"),
        "exit_hold_evaluation_id": (ev.get("exit_hold") or {}).get("evaluation_id"),
        "capital_efficiency_evaluation_id": (ev.get("capital_efficiency") or {}).get("evaluation_id"),
        "same_market_guard_decision_id": (ev.get("same_market_guard") or {}).get("decision_id"),
        "lifecycle_governance_decision_id": (ev.get("lifecycle_governance") or {}).get("decision_id"),
        "news_source_id": (ev.get("news") or {}).get("impact_id") or (ev.get("news") or {}).get("id"),
        "whale_source_id": (ev.get("whale") or {}).get("whale_event_id") or (ev.get("whale") or {}).get("id"),
        "social_source_id": (ev.get("social") or {}).get("social_link_id") or (ev.get("social") or {}).get("id"),
        "market_movement_source_id": (ev.get("market_movement") or {}).get("id"),
        "memory_source_id": (ev.get("memory") or {}).get("market_id"),
    }


def _sources(conn: Any, record: dict[str, Any], ev: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"source_table": _source_table(record["subject_type"]), "source_record_id": record["subject_id"], "source_type": record["subject_type"], "contribution_summary": "risk evidence subject"}]
    mapping = [
        ("risk", "risk_decisions", "risk_decision_id", "RISK_DECISION", "legacy risk decision input"),
        ("orderbook", "orderbook_snapshots", "orderbook_snapshot_id", "ORDERBOOK_SNAPSHOT", "critical orderbook and executable price evidence"),
        ("payout", "payout_odds_evaluations", "evaluation_id", "PAYOUT_ODDS", "supporting payout and price asymmetry evidence"),
        ("exit_hold", "exit_hold_evaluations", "evaluation_id", "EXIT_HOLD", "supporting exit versus hold evidence"),
        ("capital_efficiency", "capital_efficiency_evaluations", "evaluation_id", "CAPITAL_EFFICIENCY", "supporting capital efficiency evidence"),
        ("same_market_guard", "same_market_side_guard_decisions", "decision_id", "SAME_MARKET_GUARD", "blocking or allow exposure coherence evidence"),
        ("lifecycle_governance", "lifecycle_governance_decisions", "decision_id", "LIFECYCLE_GOVERNANCE", "governance context evidence"),
        ("news", "news_impact_scores", "impact_id", "NEWS_CONTEXT", "optional news context"),
        ("whale", "whale_events", "whale_event_id", "WHALE_CONTEXT", "optional whale context"),
        ("social", "social_market_links", "social_link_id", "SOCIAL_CONTEXT", "optional social context"),
        ("market_movement", "market_technical_signals", "id", "MARKET_MOVEMENT_CONTEXT", "optional market movement context"),
        ("memory", "market_memory_v2", "market_id", "MEMORY_CONTEXT", "optional memory context"),
    ]
    for key, table, id_key, source_type, summary in mapping:
        item = ev.get(key)
        if not item:
            continue
        source_id = item.get(id_key) or item.get("id") or item.get("market_id")
        if source_id is None:
            continue
        rows.append({"source_table": table, "source_record_id": str(source_id), "source_type": source_type, "contribution_summary": summary, "truth_state": _truth_state(conn, table, source_id, source_type)})
    return rows


def _upsert_evaluation(conn: Any, evaluation: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO risk_evidence_mesh_evaluations (
            evaluation_id, subject_type, subject_id, market_id, condition_id, side, token_id,
            critical_evidence_present_json, critical_evidence_missing_json,
            supporting_evidence_present_json, optional_context_missing_json, blocking_evidence_json,
            evidence_quality_score, edge_source_type, edge_status, risk_decision,
            risk_blocker_subtype, reason, source_refs_json, metadata_json
        ) VALUES (
            %(evaluation_id)s,%(subject_type)s,%(subject_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,
            %(critical_evidence_present_json)s,%(critical_evidence_missing_json)s,
            %(supporting_evidence_present_json)s,%(optional_context_missing_json)s,%(blocking_evidence_json)s,
            %(evidence_quality_score)s,%(edge_source_type)s,%(edge_status)s,%(risk_decision)s,
            %(risk_blocker_subtype)s,%(reason)s,%(source_refs_json)s,%(metadata_json)s
        )
        ON CONFLICT (evaluation_id) DO UPDATE SET
            critical_evidence_present_json=EXCLUDED.critical_evidence_present_json,
            critical_evidence_missing_json=EXCLUDED.critical_evidence_missing_json,
            supporting_evidence_present_json=EXCLUDED.supporting_evidence_present_json,
            optional_context_missing_json=EXCLUDED.optional_context_missing_json,
            blocking_evidence_json=EXCLUDED.blocking_evidence_json,
            evidence_quality_score=EXCLUDED.evidence_quality_score,
            edge_source_type=EXCLUDED.edge_source_type,
            edge_status=EXCLUDED.edge_status,
            risk_decision=EXCLUDED.risk_decision,
            risk_blocker_subtype=EXCLUDED.risk_blocker_subtype,
            reason=EXCLUDED.reason,
            source_refs_json=EXCLUDED.source_refs_json,
            metadata_json=EXCLUDED.metadata_json,
            updated_at=now()
        """,
        {
            **evaluation,
            "critical_evidence_present_json": Jsonb(_json_safe(evaluation["critical_evidence_present_json"])),
            "critical_evidence_missing_json": Jsonb(_json_safe(evaluation["critical_evidence_missing_json"])),
            "supporting_evidence_present_json": Jsonb(_json_safe(evaluation["supporting_evidence_present_json"])),
            "optional_context_missing_json": Jsonb(_json_safe(evaluation["optional_context_missing_json"])),
            "blocking_evidence_json": Jsonb(_json_safe(evaluation["blocking_evidence_json"])),
            "source_refs_json": Jsonb(_json_safe(evaluation["source_refs_json"])),
            "metadata_json": Jsonb(_json_safe(evaluation["metadata_json"])),
        },
    )
    for source in sources:
        conn.execute(
            """
            INSERT INTO risk_evidence_mesh_sources (
                evaluation_id,source_table,source_record_id,source_type,contribution_summary,truth_state
            ) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (evaluation["evaluation_id"], source["source_table"], str(source["source_record_id"]), source["source_type"], source["contribution_summary"], source.get("truth_state")),
        )


def _evaluation_id(record: dict[str, Any], ev: dict[str, Any], classified: dict[str, Any]) -> str:
    refs = _source_refs(ev)
    raw = "|".join(
        [
            record["subject_type"],
            str(record["subject_id"]),
            str(record.get("market_id") or ""),
            str(record.get("side") or ""),
            str(classified["risk_decision"]),
            str(classified["risk_blocker_subtype"]),
            ",".join(str(refs.get(key) or "") for key in sorted(refs)),
        ]
    )
    return f"risk_evidence_mesh_{uuid5(NAMESPACE_URL, raw).hex}"


def _score(present: set[str], supporting: set[str], missing: set[str], blocking: set[str], optional_missing: set[str]) -> float:
    value = Decimal(len(present) * 2 + len(supporting))
    total = value + Decimal(len(missing) * 2 + len(blocking) * 4 + max(0, len(optional_missing) - 1))
    if total <= 0:
        return 0.0
    return _float(max(Decimal("0"), min(Decimal("1"), value / total)))


def _lineage_classification(classified: dict[str, Any]) -> dict[str, Any]:
    subtype = classified.get("risk_blocker_subtype")
    if subtype == "RISK_BLOCKED_LINEAGE_CRITICAL":
        status = "CRITICAL_LINEAGE_MISSING"
    elif subtype == "RISK_REVIEW_LINEAGE_PARTIAL":
        status = "PARTIAL_LINEAGE_NON_BLOCKING"
    else:
        status = "LINEAGE_NOT_PRIMARY"
    return {"status": status, "critical_missing": classified.get("critical_evidence_missing_json", [])}


def _source_table(subject_type: str) -> str:
    return {
        "FRESH_SEED": "fresh_candidate_seeds",
        "PAPER_CANDIDATE": "paper_eligibility_candidates",
        "PAPER_INTENT": "paper_intents",
        "PAPER_POSITION": "paper_positions",
        "LIFECYCLE_PLAN": "trade_lifecycle_plans",
    }.get(subject_type, "unknown")


def _truth_state(conn: Any, source_table: str, source_id: Any, source_type: str) -> str | None:
    if not _table_exists(conn, "truth_state_registry"):
        return None
    row = _fetchone(
        conn,
        """
        SELECT truth_state
        FROM truth_state_registry
        WHERE source_table=%s AND source_record_id=%s AND source_type=%s
        ORDER BY updated_at DESC,id DESC LIMIT 1
        """,
        (source_table, str(source_id), source_type),
    )
    return _text((row or {}).get("truth_state"))


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "risk_evidence_mesh_evaluations") and _table_exists(conn, "risk_evidence_mesh_sources")


def _table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _fetchone(conn: Any, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(query, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def _jsonb_item_counts(conn: Any, column: str, limit: int) -> dict[str, int]:
    rows = _fetchall(
        conn,
        f"""
        SELECT item, COUNT(*) AS count
        FROM risk_evidence_mesh_evaluations,
             jsonb_array_elements_text({column}) AS item
        GROUP BY item
        ORDER BY count DESC,item
        LIMIT %s
        """,
        (limit,),
    )
    return {str(row["item"]): _int(row["count"]) for row in rows}


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _safety_counts(conn: Any) -> dict[str, int]:
    return {
        table: _count_table(conn, table)
        for table in (
            "paper_intents",
            "paper_orders",
            "paper_fills",
            "paper_positions",
            "paper_position_closes",
            "paper_capital_ledger",
            "live_orders",
            "orders_v2",
            "fills_v2",
            "positions",
        )
    }


def _governance_trace_summary(conn: Any, *, limit: int) -> dict[str, Any]:
    if not _table_exists(conn, "lifecycle_governance_decisions"):
        return _empty_governance_trace()
    totals = _fetchone(
        conn,
        """
        SELECT
          COUNT(*) FILTER (WHERE metadata_json->'risk_source_trace'->>'selected_risk_source'='RISK_EVIDENCE_MESH') AS risk_evidence_used_count,
          COUNT(*) FILTER (WHERE COALESCE((metadata_json->'risk_source_trace'->>'legacy_ignored')::boolean,false)) AS legacy_risk_ignored_count,
          COUNT(*) FILTER (WHERE metadata_json->'risk_source_trace'->>'ignored_reason' ILIKE 'Fresh non-blocking Risk Evidence Mesh evaluation selected over stale legacy risk block%%') AS stale_legacy_risk_block_ignored_count,
          COUNT(*) FILTER (
            WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
              AND actionability_class='WATCH_FOR_CONFIRMATION'
          ) AS risk_review_promoted_to_watch_count,
          COUNT(*) FILTER (
            WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
              AND actionability_class='HARD_BLOCK'
          ) AS risk_review_kept_blocked_count,
          COUNT(*) FILTER (
            WHERE metadata_json->'risk_source_trace'->>'final_risk_interpretation'='RISK_REVIEW'
              AND actionability_class IN ('ACTIONABLE_SMALL_PAPER','ACTIONABLE_STANDARD_PAPER','COMPLETE_HIGH_CONFIDENCE')
          ) AS risk_review_actionable_count
        FROM lifecycle_governance_decisions
        """,
    ) or {}
    selection = _fetchall(
        conn,
        """
        SELECT COALESCE(metadata_json->'risk_source_trace'->>'selected_risk_source','UNKNOWN') AS selected_risk_source,
               COALESCE(metadata_json->'risk_source_trace'->>'selected_risk_source_freshness','UNKNOWN') AS selected_risk_source_freshness,
               COUNT(*) AS count
        FROM lifecycle_governance_decisions
        GROUP BY selected_risk_source, selected_risk_source_freshness
        ORDER BY count DESC, selected_risk_source
        LIMIT %s
        """,
        (limit,),
    )
    traces = _fetchall(
        conn,
        """
        SELECT decision_id, subject_type, subject_id, market_id, side, actionability_class,
               metadata_json->'risk_source_trace' AS risk_source_trace,
               critical_blockers_json, created_at
        FROM lifecycle_governance_decisions
        WHERE metadata_json->'risk_source_trace'->>'selected_risk_source'='RISK_EVIDENCE_MESH'
        ORDER BY created_at DESC,id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return {
        "risk_evidence_used_count": _int(totals.get("risk_evidence_used_count")),
        "legacy_risk_ignored_count": _int(totals.get("legacy_risk_ignored_count")),
        "stale_legacy_risk_block_ignored_count": _int(totals.get("stale_legacy_risk_block_ignored_count")),
        "risk_review_promoted_to_watch_count": _int(totals.get("risk_review_promoted_to_watch_count")),
        "risk_review_kept_blocked_count": _int(totals.get("risk_review_kept_blocked_count")),
        "risk_review_actionable_count": _int(totals.get("risk_review_actionable_count")),
        "risk_source_selection_summary": selection,
        "latest_risk_review_traces": traces,
    }


def _empty_governance_trace() -> dict[str, Any]:
    return {
        "risk_evidence_used_count": 0,
        "legacy_risk_ignored_count": 0,
        "stale_legacy_risk_block_ignored_count": 0,
        "risk_review_promoted_to_watch_count": 0,
        "risk_review_kept_blocked_count": 0,
        "risk_review_actionable_count": 0,
        "risk_source_selection_summary": [],
        "latest_risk_review_traces": [],
    }


def _empty(status: str, generated_at: str) -> dict[str, Any]:
    return {
        "mock_data": False,
        "status": status,
        "generated_at": generated_at,
        "total_evaluations": 0,
        "RISK_SUPPORT": 0,
        "RISK_WATCH": 0,
        "RISK_REVIEW": 0,
        "RISK_BLOCK": 0,
        "security_governance_status": SECURITY_GOVERNANCE_STATUS,
        **_empty_governance_trace(),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _age_seconds(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - value.astimezone(UTC)).total_seconds()))


def _sort_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
