from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.capital_efficiency import CapitalEfficiencyService


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
SUBJECT_TYPES = {"PAPER_POSITION", "PAPER_CANDIDATE", "PAPER_INTENT"}
DECISIONS = {
    "EXIT_NOW",
    "HOLD_TO_RESOLUTION",
    "PARTIAL_EXIT_REVIEW",
    "HOLD_REVIEW",
    "EMERGENCY_EXIT_REVIEW",
    "WAIT",
    "INSUFFICIENT_DATA",
}


class ExitHoldReasoningService:
    """Derived exit-now vs hold-to-resolution reasoning.

    This service has no exit authority. It creates only source-linked reasoning rows.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def evaluate_recent(self, *, limit: int = 100, subject_type: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        subject = str(subject_type).upper() if subject_type else None
        if subject and subject not in SUBJECT_TYPES:
            return {"mock_data": False, "status": "INVALID_SUBJECT_TYPE", "evaluations_created": 0}
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluations_created": 0}
        with self._factory.connect() as conn, conn.transaction():
            if not _tables_ready(conn):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluations_created": 0}
            before = _count_table(conn, "exit_hold_evaluations")
            safety_before = _safety_counts(conn)
            records = self._records(conn, subject_type=subject, limit=limit)
            outcomes = [self._evaluate_record(conn, record, dry_run=dry_run) for record in records]
            after = _count_table(conn, "exit_hold_evaluations")
            safety_after = _safety_counts(conn)
        counts = Counter(item["decision"] for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "evaluations_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_decision": dict(counts),
                "latest_outcomes": outcomes[:20],
                "safety_before": safety_before,
                "safety_after": safety_after,
                "trading_mutation": _trading_mutation(safety_before, safety_after),
            }
        )

    def evaluate_subject_with_conn(self, conn: Any, *, subject_type: str, subject_id: str, dry_run: bool = False) -> dict[str, Any]:
        if not _tables_ready(conn):
            return {"status": "MISSING_TABLES", "subject_type": subject_type, "subject_id": subject_id}
        record = self._record_by_subject(conn, subject_type=subject_type, subject_id=subject_id)
        if record is None:
            return {"status": "SUBJECT_NOT_FOUND", "subject_type": subject_type, "subject_id": subject_id}
        return self._evaluate_record(conn, record, dry_run=dry_run)

    def dashboard_summary(self, *, limit: int = 50) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        if not self._factory.enabled:
            return _empty_dashboard("DATABASE_UNAVAILABLE", generated_at)
        with self._factory.connect() as conn:
            if not _table_exists(conn, "exit_hold_evaluations"):
                return _empty_dashboard("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE decision='EXIT_NOW') AS exit_now_count,
                  COUNT(*) FILTER (WHERE decision='HOLD_TO_RESOLUTION') AS hold_count,
                  COUNT(*) FILTER (WHERE decision='PARTIAL_EXIT_REVIEW') AS partial_count,
                  COUNT(*) FILTER (WHERE decision='EMERGENCY_EXIT_REVIEW') AS emergency_count,
                  COUNT(*) FILTER (WHERE decision='INSUFFICIENT_DATA') AS insufficient_count,
                  COUNT(*) FILTER (WHERE missing_inputs_json ? 'TIME_TO_RESOLUTION_MISSING') AS missing_time_count,
                  COUNT(*) FILTER (WHERE missing_inputs_json ? 'EXIT_NOW_UNAVAILABLE') AS missing_exit_price_count
                FROM exit_hold_evaluations
                """,
            ) or {}
            by_decision = _fetchall(conn, "SELECT decision, COUNT(*) AS count FROM exit_hold_evaluations GROUP BY decision ORDER BY decision")
            latest = _latest_rows(conn, "TRUE", limit)
            open_rows = _latest_rows(conn, "subject_type='PAPER_POSITION'", limit)
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(conn, limit=limit)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_evaluations": _int(totals.get("total")),
                "evaluations_by_decision": {str(row["decision"]): _int(row["count"]) for row in by_decision},
                "open_position_evaluations": open_rows,
                "exit_now_count": _int(totals.get("exit_now_count")),
                "hold_to_resolution_count": _int(totals.get("hold_count")),
                "partial_exit_review_count": _int(totals.get("partial_count")),
                "emergency_exit_review_count": _int(totals.get("emergency_count")),
                "insufficient_data_count": _int(totals.get("insufficient_count")),
                "missing_time_to_resolution_count": _int(totals.get("missing_time_count")),
                "missing_exit_price_count": _int(totals.get("missing_exit_price_count")),
                "latest_evaluations": latest,
                "capital_efficiency_visibility": capital_efficiency,
                "capital_efficiency_observational_only": True,
            }
        )

    def detail(self, evaluation_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluation_id": evaluation_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "exit_hold_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluation_id": evaluation_id}
            row = _fetchone(conn, "SELECT * FROM exit_hold_evaluations WHERE evaluation_id=%s", (evaluation_id,))
            if not row:
                return {"mock_data": False, "status": "NOT_FOUND", "evaluation_id": evaluation_id}
            sources = _fetchall(conn, "SELECT * FROM exit_hold_sources WHERE evaluation_id=%s ORDER BY linked_at,id", (evaluation_id,))
            related = _related_subject(conn, row)
            capital_efficiency = CapitalEfficiencyService(connection_factory=self._factory).observational_summary_for_market(
                conn,
                market_id=str(row.get("market_id")) if row.get("market_id") else None,
                position_id=str(row.get("paper_position_id")) if row.get("paper_position_id") else None,
            )
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "evaluation": row,
                "sources": sources,
                "related_subject": related,
                "payout_odds_link": _dict(row.get("source_refs_json")).get("payout_odds_evaluation_id"),
                "forensics_link": f"/dashboard/api/v2/paper/trade-forensics/{row.get('paper_position_id')}" if row.get("paper_position_id") else None,
                "capital_efficiency_visibility": capital_efficiency,
                "capital_efficiency_observational_only": True,
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "exit_hold_evaluations"):
            return None
        return _fetchone(
            conn,
            """
            SELECT * FROM exit_hold_evaluations
            WHERE subject_type=%s AND subject_id=%s
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (subject_type, subject_id),
        )

    def observational_summary_for_market(self, conn: Any, *, market_id: str | None = None, position_id: str | None = None, limit: int = 5) -> dict[str, Any]:
        if not _table_exists(conn, "exit_hold_evaluations"):
            return {"status": "MISSING_TABLES", "latest_evaluations": [], "observational_only": True}
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id=%s")
            params.append(str(market_id))
        if position_id:
            clauses.append("paper_position_id=%s")
            params.append(str(position_id))
        where = " OR ".join(clauses) if clauses else "TRUE"
        params.append(limit)
        rows = _fetchall(conn, f"SELECT evaluation_id,subject_type,subject_id,market_id,side,exit_now_value,exit_now_pnl,hold_to_resolution_value,hold_to_resolution_profit_if_win,decision,reason,missing_inputs_json,created_at FROM exit_hold_evaluations WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s", tuple(params))
        return _json_safe({"status": "OK", "latest_evaluations": rows, "observational_only": True})

    def _records(self, conn: Any, *, subject_type: str | None, limit: int) -> list[dict[str, Any]]:
        wanted = [subject_type] if subject_type else ["PAPER_POSITION", "PAPER_INTENT", "PAPER_CANDIDATE"]
        rows: list[dict[str, Any]] = []
        if "PAPER_POSITION" in wanted:
            rows.extend(_position_records(conn, limit=limit))
        if "PAPER_INTENT" in wanted:
            rows.extend(_intent_records(conn, limit=limit))
        if "PAPER_CANDIDATE" in wanted:
            rows.extend(_candidate_records(conn, limit=limit))
        return rows

    def _record_by_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if subject_type == "PAPER_POSITION":
            rows = _position_records(conn, limit=1, subject_id=subject_id)
        elif subject_type == "PAPER_INTENT":
            rows = _intent_records(conn, limit=1, subject_id=subject_id)
        else:
            rows = _candidate_records(conn, limit=1, subject_id=subject_id)
        return rows[0] if rows else None

    def _evaluate_record(self, conn: Any, record: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        payout = _latest_payout(conn, subject_type=record["subject_type"], subject_id=record["subject_id"])
        if not payout and record["subject_type"] == "PAPER_POSITION":
            payout = _latest_payout(conn, subject_type="PAPER_POSITION", subject_id=record["subject_id"])
        book = _latest_book(conn, record.get("market_id"), record.get("side"))
        timing = _time_info(conn, record.get("market_id"))
        rules = _rules_info(conn, record.get("market_id"))
        reactions = _position_reactions(conn, record.get("paper_position_id"))

        values = _build_values(record, payout, book)
        missing = values.pop("missing")
        missing.extend(timing["missing"])
        rules_risk = rules["rules_risk"]
        spread_risk = _spread_risk(book)
        liquidity = _liquidity_quality(book)
        risk_of_reversal = _risk_of_reversal(record, rules_risk, reactions)
        decision, reason = _decision(record, values, missing, timing, liquidity, spread_risk, rules_risk, risk_of_reversal)
        evaluation = {
            "evaluation_id": _evaluation_id(record, book, payout, decision),
            "subject_type": record["subject_type"],
            "subject_id": record["subject_id"],
            "paper_position_id": record.get("paper_position_id"),
            "market_id": record.get("market_id"),
            "condition_id": record.get("condition_id"),
            "side": record.get("side"),
            "token_id": record.get("token_id") or (book or {}).get("token_id"),
            "time_to_resolution_seconds": timing["seconds"],
            "liquidity_exit_quality": liquidity,
            "spread": (book or {}).get("spread"),
            "spread_risk": spread_risk,
            "rules_risk": rules_risk,
            "risk_of_reversal": risk_of_reversal,
            "decision": decision,
            "confidence": None,
            "reason": reason,
            "missing_inputs_json": sorted(set(missing)),
            "source_refs_json": {
                "payout_odds_evaluation_id": (payout or {}).get("evaluation_id"),
                "orderbook_snapshot_id": (book or {}).get("id"),
                "rules_analysis_id": rules.get("rules_analysis_id"),
                "market_rules_id": rules.get("market_rules_id"),
            },
            "metadata_json": {
                "observational_only": True,
                "no_auto_exit": True,
                "position_reactions": reactions,
                "rules_summary": rules,
                "time_source": timing.get("source"),
            },
            **values,
        }
        sources = _sources(record, payout, book, rules, timing)
        if not dry_run:
            _upsert(conn, evaluation, sources)
        return _json_safe({"evaluation_id": evaluation["evaluation_id"], "subject_type": record["subject_type"], "subject_id": record["subject_id"], "decision": decision, "reason": reason, "dry_run": dry_run})


def _position_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    where = "WHERE pp.id::text=%s" if subject_id else "WHERE pp.current_status IN ('OPEN','EXIT_PENDING') AND pp.closed_at IS NULL AND COALESCE(pp.excluded_from_active_paper_truth,false)=false"
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(conn, f"SELECT 'PAPER_POSITION' AS subject_type, pp.id::text AS subject_id, pp.id::text AS paper_position_id, pp.market_id, pp.intended_outcome AS side, pp.avg_entry AS entry_price, pp.size AS quantity, pp.mark_price, pp.unrealized, pp.opened_at, pp.payload_json, mv.condition_id FROM paper_positions pp LEFT JOIN markets_v2 mv ON mv.market_id=pp.market_id {where} ORDER BY pp.opened_at DESC NULLS LAST LIMIT %s", tuple(params))


def _intent_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    where = "WHERE pi.paper_intent_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(conn, f"SELECT 'PAPER_INTENT' AS subject_type, pi.paper_intent_id AS subject_id, pi.market_id, pi.side, pi.intended_price AS entry_price, pi.evidence, mv.condition_id FROM paper_intents pi LEFT JOIN markets_v2 mv ON mv.market_id=pi.market_id {where} ORDER BY pi.created_at DESC, pi.id DESC LIMIT %s", tuple(params))
    for row in rows:
        evidence = _dict(row.get("evidence"))
        row["quantity"] = _decimal_or_none(evidence.get("quantity"))
    return rows


def _candidate_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    where = "WHERE pec.eligibility_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(conn, f"SELECT 'PAPER_CANDIDATE' AS subject_type, pec.eligibility_id AS subject_id, pec.market_id, pec.side, pec.evidence, mv.condition_id FROM paper_eligibility_candidates pec LEFT JOIN markets_v2 mv ON mv.market_id=pec.market_id {where} ORDER BY pec.updated_at DESC, pec.id DESC LIMIT %s", tuple(params))
    for row in rows:
        evidence = _dict(row.get("evidence"))
        row["entry_price"] = _decimal_or_none(evidence.get("orderbook_best_ask") or _dict(evidence.get("source_evidence")).get("orderbook_best_ask"))
        row["quantity"] = _decimal_or_none(evidence.get("quantity"))
    return rows


def _latest_payout(conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "payout_odds_evaluations"):
        return None
    return _fetchone(conn, "SELECT * FROM payout_odds_evaluations WHERE subject_type=%s AND subject_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (subject_type, subject_id))


def _latest_book(conn: Any, market_id: Any, side: Any) -> dict[str, Any] | None:
    if not market_id or not side or not _table_exists(conn, "orderbook_snapshots"):
        return None
    return _fetchone(conn, "SELECT * FROM orderbook_snapshots WHERE market_id=%s AND side=%s AND COALESCE(is_stale,false)=false ORDER BY snapshot_at DESC NULLS LAST,collected_at DESC NULLS LAST,id DESC LIMIT 1", (str(market_id), str(side).upper()))


def _time_info(conn: Any, market_id: Any) -> dict[str, Any]:
    if not market_id:
        return {"seconds": None, "missing": ["TIME_TO_RESOLUTION_MISSING"], "source": None}
    for table, col, order_col in (
        ("markets_v2", "COALESCE(resolution_time, close_time)", "updated_at"),
        ("market_rules", "deadline_at", "updated_at"),
        ("rules_analysis", "deadline_at", "created_at"),
    ):
        if not _table_exists(conn, table):
            continue
        row = _fetchone(conn, f"SELECT {col} AS deadline FROM {table} WHERE market_id=%s ORDER BY {order_col} DESC NULLS LAST, id DESC LIMIT 1", (str(market_id),))
        deadline = row.get("deadline") if row else None
        if deadline:
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            return {"seconds": max(0, int((deadline - datetime.now(UTC)).total_seconds())), "missing": [], "source": table}
    return {"seconds": None, "missing": ["TIME_TO_RESOLUTION_MISSING"], "source": None}


def _rules_info(conn: Any, market_id: Any) -> dict[str, Any]:
    result = {"rules_risk": "RULES_RISK_UNKNOWN", "rules_analysis_id": None, "market_rules_id": None}
    if not market_id:
        return result
    if _table_exists(conn, "rules_analysis"):
        row = _fetchone(conn, "SELECT * FROM rules_analysis WHERE market_id=%s ORDER BY created_at DESC,id DESC LIMIT 1", (str(market_id),))
        if row:
            result["rules_analysis_id"] = row.get("rules_analysis_id")
            rec = str(row.get("recommendation") or "").upper()
            wr = _decimal(row.get("wording_risk"))
            dr = _decimal(row.get("dispute_risk"))
            if rec in {"BLOCK", "NO_TRADE", "PENALIZE_HEAVILY"} or wr >= Decimal("0.35") or dr >= Decimal("0.50"):
                result["rules_risk"] = "HIGH"
            elif wr > 0 or dr > 0:
                result["rules_risk"] = "MEDIUM"
            else:
                result["rules_risk"] = "LOW"
    if _table_exists(conn, "market_rules"):
        row = _fetchone(conn, "SELECT id,resolution_source_status,resolution_source_hard_block FROM market_rules WHERE market_id=%s ORDER BY updated_at DESC,id DESC LIMIT 1", (str(market_id),))
        if row:
            result["market_rules_id"] = row.get("id")
            if row.get("resolution_source_hard_block"):
                result["rules_risk"] = "HIGH"
            elif str(row.get("resolution_source_status") or "").upper() in {"AMBIGUOUS", "MISSING"} and result["rules_risk"] == "LOW":
                result["rules_risk"] = "MEDIUM"
    return result


def _position_reactions(conn: Any, position_id: Any) -> list[str]:
    if not position_id or not _table_exists(conn, "position_reactions"):
        return []
    rows = _fetchall(conn, "SELECT reaction_type,severity FROM position_reactions WHERE position_id=%s ORDER BY created_at DESC LIMIT 20", (str(position_id),))
    return [str(row.get("reaction_type")) for row in rows]


def _build_values(record: dict[str, Any], payout: dict[str, Any] | None, book: dict[str, Any] | None) -> dict[str, Any]:
    entry = _decimal_or_none(record.get("entry_price"))
    qty = _decimal_or_none(record.get("quantity"))
    missing: list[str] = []
    if not payout:
        missing.append("PAYOUT_ODDS_MISSING")
    if entry is None or qty is None:
        missing.append("BASIC_POSITION_DATA_MISSING")
    cost = _decimal_or_none((payout or {}).get("stake_usd")) or (entry * qty if entry is not None and qty is not None else None)
    hold_value = _decimal_or_none((payout or {}).get("payout_if_win"))
    hold_profit = _decimal_or_none((payout or {}).get("profit_if_win"))
    hold_loss = _decimal_or_none((payout or {}).get("max_loss")) or cost
    bid = _decimal_or_none((book or {}).get("best_bid"))
    if bid is None or qty is None:
        missing.append("EXIT_NOW_UNAVAILABLE")
        exit_value = None
        exit_pnl = None
    else:
        exit_value = bid * qty
        exit_pnl = exit_value - (cost or Decimal("0"))
    return {
        "cost_basis": cost,
        "quantity": qty,
        "entry_price": entry,
        "current_exit_price": bid,
        "exit_now_value": exit_value,
        "exit_now_pnl": exit_pnl,
        "hold_to_resolution_value": hold_value,
        "hold_to_resolution_profit_if_win": hold_profit,
        "hold_to_resolution_max_loss": hold_loss,
        "missing": missing,
    }


def _decision(record: dict[str, Any], v: dict[str, Any], missing: list[str], timing: dict[str, Any], liquidity: str, spread_risk: str, rules_risk: str, risk_of_reversal: str) -> tuple[str, str]:
    if "PAYOUT_ODDS_MISSING" in missing or "BASIC_POSITION_DATA_MISSING" in missing:
        return "INSUFFICIENT_DATA", "Missing payout odds or basic position data; no exit/hold decision is safe."
    if record["subject_type"] == "PAPER_POSITION" and "EXIT_NOW_UNAVAILABLE" in missing:
        return "EMERGENCY_EXIT_REVIEW", "Current exit price is unavailable for an open position."
    exit_pnl = _decimal_or_none(v.get("exit_now_pnl")) or Decimal("0")
    hold_profit = _decimal_or_none(v.get("hold_to_resolution_profit_if_win")) or Decimal("0")
    hold_extra = hold_profit - exit_pnl
    short_time = timing.get("seconds") is not None and int(timing["seconds"]) <= 3 * 24 * 3600
    risk_rising = risk_of_reversal in {"HIGH", "MEDIUM"} or rules_risk == "HIGH"
    if exit_pnl > 0 and hold_extra <= max(Decimal("0.05"), abs(exit_pnl) * Decimal("0.25")) and liquidity == "GOOD":
        return "EXIT_NOW", "Exit PnL is positive, exit liquidity is good, and remaining hold upside is small."
    if exit_pnl > 0 and hold_extra > 0 and risk_rising and liquidity in {"GOOD", "FAIR"}:
        return "PARTIAL_EXIT_REVIEW", "Profit exists, hold upside remains, and risk is rising."
    if short_time and rules_risk in {"LOW", "MEDIUM"} and liquidity in {"GOOD", "FAIR"} and hold_profit > exit_pnl:
        return "HOLD_TO_RESOLUTION", "Time to resolution is short and hold-to-resolution value exceeds exit-now value."
    if exit_pnl < 0 and "EXIT_NOW_UNAVAILABLE" not in missing:
        return "HOLD_REVIEW", "Position is not profitable at current bid; review hold thesis without auto-exit."
    if "TIME_TO_RESOLUTION_MISSING" in missing or rules_risk == "RULES_RISK_UNKNOWN":
        return "WAIT", "Core values exist but time or rules evidence is incomplete."
    return "WAIT", "No strong exit or hold signal from source-backed evidence."


def _liquidity_quality(book: dict[str, Any] | None) -> str:
    if not book or book.get("best_bid") is None:
        return "EXIT_LIQUIDITY_UNKNOWN"
    score = _decimal(book.get("liquidity_score"))
    spread = _decimal(book.get("spread"))
    if score >= Decimal("0.75") and spread <= Decimal("0.03"):
        return "GOOD"
    if score >= Decimal("0.25"):
        return "FAIR"
    return "POOR"


def _spread_risk(book: dict[str, Any] | None) -> str:
    if not book or book.get("spread") is None:
        return "SPREAD_RISK_UNKNOWN"
    spread = _decimal(book.get("spread"))
    if spread >= Decimal("0.08"):
        return "HIGH"
    if spread >= Decimal("0.03"):
        return "MEDIUM"
    return "LOW"


def _risk_of_reversal(record: dict[str, Any], rules_risk: str, reactions: list[str]) -> str:
    adverse = {"ADVERSE_NEWS", "LIQUIDITY_DROP", "SPREAD_WIDENED", "RISK_INCREASED", "EXIT_DEGRADED", "PNL_FALLING", "CAPITAL_PRESSURE"}
    if rules_risk == "HIGH" or any(item in adverse for item in reactions):
        return "HIGH"
    if rules_risk == "MEDIUM":
        return "MEDIUM"
    return "UNKNOWN"


def _sources(record: dict[str, Any], payout: dict[str, Any] | None, book: dict[str, Any] | None, rules: dict[str, Any], timing: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [{"source_table": _source_table(record["subject_type"]), "source_record_id": record["subject_id"], "source_type": record["subject_type"], "contribution_summary": "subject source for exit/hold reasoning"}]
    if payout:
        sources.append({"source_table": "payout_odds_evaluations", "source_record_id": payout["evaluation_id"], "source_type": "PAYOUT_ODDS", "contribution_summary": "hold-to-resolution value source"})
    if book:
        sources.append({"source_table": "orderbook_snapshots", "source_record_id": str(book["id"]), "source_type": "EXIT_NOW_PRICE", "contribution_summary": "current best bid and liquidity source"})
    if rules.get("rules_analysis_id"):
        sources.append({"source_table": "rules_analysis", "source_record_id": str(rules["rules_analysis_id"]), "source_type": "RULES_RISK", "contribution_summary": "rules and wording risk source"})
    if rules.get("market_rules_id"):
        sources.append({"source_table": "market_rules", "source_record_id": str(rules["market_rules_id"]), "source_type": "TIME_RULES", "contribution_summary": "deadline/resolution source"})
    if timing.get("source"):
        sources.append({"source_table": str(timing["source"]), "source_record_id": str(record.get("market_id")), "source_type": "TIME_TO_RESOLUTION", "contribution_summary": "time-to-resolution source"})
    return sources


def _upsert(conn: Any, ev: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO exit_hold_evaluations (
            evaluation_id, subject_type, subject_id, paper_position_id, market_id, condition_id, side, token_id,
            cost_basis, quantity, entry_price, current_exit_price, exit_now_value, exit_now_pnl,
            hold_to_resolution_value, hold_to_resolution_profit_if_win, hold_to_resolution_max_loss,
            time_to_resolution_seconds, liquidity_exit_quality, spread, spread_risk, rules_risk,
            risk_of_reversal, decision, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
        )
        VALUES (
            %(evaluation_id)s,%(subject_type)s,%(subject_id)s,%(paper_position_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,
            %(cost_basis)s,%(quantity)s,%(entry_price)s,%(current_exit_price)s,%(exit_now_value)s,%(exit_now_pnl)s,
            %(hold_to_resolution_value)s,%(hold_to_resolution_profit_if_win)s,%(hold_to_resolution_max_loss)s,
            %(time_to_resolution_seconds)s,%(liquidity_exit_quality)s,%(spread)s,%(spread_risk)s,%(rules_risk)s,
            %(risk_of_reversal)s,%(decision)s,%(confidence)s,%(reason)s,%(missing_inputs_json)s,%(source_refs_json)s,%(metadata_json)s
        )
        ON CONFLICT (evaluation_id) DO UPDATE SET updated_at=now(), metadata_json=EXCLUDED.metadata_json
        """,
        {**ev, "missing_inputs_json": Jsonb(ev["missing_inputs_json"]), "source_refs_json": Jsonb(_json_safe(ev["source_refs_json"])), "metadata_json": Jsonb(_json_safe(ev["metadata_json"]))},
    )
    for source in sources:
        conn.execute("INSERT INTO exit_hold_sources (evaluation_id,source_table,source_record_id,source_type,contribution_summary) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (ev["evaluation_id"], source["source_table"], str(source["source_record_id"]), source["source_type"], source["contribution_summary"]))


def _evaluation_id(record: dict[str, Any], book: dict[str, Any] | None, payout: dict[str, Any] | None, decision: str) -> str:
    raw = "|".join([record["subject_type"], str(record["subject_id"]), str((book or {}).get("id")), str((payout or {}).get("evaluation_id")), decision])
    return f"exit_hold_{uuid5(NAMESPACE_URL, raw).hex}"


def _source_table(subject_type: str) -> str:
    return {"PAPER_POSITION": "paper_positions", "PAPER_INTENT": "paper_intents", "PAPER_CANDIDATE": "paper_eligibility_candidates"}[subject_type]


def _related_subject(conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
    table = _source_table(str(row["subject_type"]))
    col = {"PAPER_POSITION": "id::text", "PAPER_INTENT": "paper_intent_id", "PAPER_CANDIDATE": "eligibility_id"}[str(row["subject_type"])]
    return _fetchone(conn, f"SELECT * FROM {table} WHERE {col}=%s LIMIT 1", (str(row["subject_id"]),)) if _table_exists(conn, table) else None


def _latest_rows(conn: Any, where: str, limit: int) -> list[dict[str, Any]]:
    return _fetchall(conn, f"SELECT evaluation_id,subject_type,subject_id,paper_position_id,market_id,side,exit_now_value,exit_now_pnl,hold_to_resolution_value,hold_to_resolution_profit_if_win,time_to_resolution_seconds,liquidity_exit_quality,spread_risk,rules_risk,risk_of_reversal,decision,reason,missing_inputs_json,created_at FROM exit_hold_evaluations WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s", (limit,))


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "exit_hold_evaluations") and _table_exists(conn, "exit_hold_sources")


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _count_table(conn: Any, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]) if _table_exists(conn, table) else 0


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {t: _count_table(conn, t) for t in ["paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions"]}
    if _table_exists(conn, "paper_accounts"):
        row = _fetchone(conn, "SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'")
        counts["capital_balances"] = row
    return _json_safe(counts)


def _trading_mutation(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before != after


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {"mock_data": False, "status": status, "generated_at": generated_at, "security_governance_status": SECURITY_GOVERNANCE_STATUS, "total_evaluations": 0, "evaluations_by_decision": {}, "open_position_evaluations": [], "exit_now_count": 0, "hold_to_resolution_count": 0, "partial_exit_review_count": 0, "emergency_exit_review_count": 0, "insufficient_data_count": 0, "missing_time_to_resolution_count": 0, "missing_exit_price_count": 0, "latest_evaluations": []}
