from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.trade_thesis_engine import TradeThesisEngine


SECURITY_GOVERNANCE_STATUS = "YELLOW_ACCEPTED_BY_OPERATOR"
SUBJECT_TYPES = {"PAPER_POSITION", "PAPER_CANDIDATE", "PAPER_INTENT", "FRESH_SEED"}
RECOMMENDATIONS = {
    "CAPITAL_SUPPORT",
    "CAPITAL_WATCH",
    "CAPITAL_REDUCE_REVIEW",
    "CAPITAL_RELEASE_REVIEW",
    "CAPITAL_BLOCK",
    "CAPITAL_INSUFFICIENT_DATA",
}
MIN_HOURS = Decimal("0.0166666667")


class CapitalEfficiencyService:
    """Derived reward-per-dollar-time reasoning.

    This service writes only source-linked reasoning records. It has no trading,
    balance, position, or exit authority.
    """

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, account_id: str = "paper_default") -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._account_id = account_id

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
            before = _count_table(conn, "capital_efficiency_evaluations")
            safety_before = _safety_counts(conn)
            records = self._records(conn, subject_type=subject, limit=limit)
            outcomes = [self._evaluate_record(conn, record, dry_run=dry_run) for record in records]
            after = _count_table(conn, "capital_efficiency_evaluations")
            safety_after = _safety_counts(conn)
        counts = Counter(item["recommendation"] for item in outcomes)
        return _json_safe(
            {
                "mock_data": False,
                "status": "DRY_RUN" if dry_run else "OK",
                "generated_at": generated_at,
                "subjects_checked": len(records),
                "evaluations_created": 0 if dry_run else max(0, after - before),
                "outcomes_by_recommendation": dict(counts),
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
            if not _table_exists(conn, "capital_efficiency_evaluations"):
                return _empty_dashboard("MISSING_TABLES", generated_at)
            totals = _fetchone(
                conn,
                """
                SELECT
                  COUNT(*) AS total,
                  COALESCE(AVG(capital_efficiency_score),0) AS avg_score,
                  COALESCE(AVG(reward_per_dollar_hour),0) AS avg_reward_per_dollar_hour,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_SUPPORT') AS support_count,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_WATCH') AS watch_count,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_REDUCE_REVIEW') AS reduce_count,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_RELEASE_REVIEW') AS release_count,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_BLOCK') AS block_count,
                  COUNT(*) FILTER (WHERE recommendation='CAPITAL_INSUFFICIENT_DATA') AS insufficient_count,
                  COUNT(*) FILTER (WHERE missing_inputs_json ? 'TIME_TO_RESOLUTION_MISSING') AS missing_time_count
                FROM capital_efficiency_evaluations
                """,
            ) or {}
            by_subject = _fetchall(conn, "SELECT subject_type, COUNT(*) AS count FROM capital_efficiency_evaluations GROUP BY subject_type ORDER BY subject_type")
            by_rec = _fetchall(conn, "SELECT recommendation, COUNT(*) AS count FROM capital_efficiency_evaluations GROUP BY recommendation ORDER BY recommendation")
            latest = _latest_rows(conn, "TRUE", limit)
            open_rows = _latest_rows(conn, "subject_type='PAPER_POSITION'", limit)
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": generated_at,
                "security_governance_status": SECURITY_GOVERNANCE_STATUS,
                "total_evaluations": _int(totals.get("total")),
                "evaluations_by_subject_type": {str(row["subject_type"]): _int(row["count"]) for row in by_subject},
                "recommendations_by_type": {str(row["recommendation"]): _int(row["count"]) for row in by_rec},
                "avg_capital_efficiency_score": _float(totals.get("avg_score")),
                "avg_reward_per_dollar_hour": _float(totals.get("avg_reward_per_dollar_hour")),
                "open_position_evaluations": open_rows,
                "capital_support_count": _int(totals.get("support_count")),
                "capital_watch_count": _int(totals.get("watch_count")),
                "capital_reduce_review_count": _int(totals.get("reduce_count")),
                "capital_release_review_count": _int(totals.get("release_count")),
                "capital_block_count": _int(totals.get("block_count")),
                "insufficient_data_count": _int(totals.get("insufficient_count")),
                "missing_time_to_resolution_count": _int(totals.get("missing_time_count")),
                "latest_evaluations": latest,
            }
        )

    def detail(self, evaluation_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"mock_data": False, "status": "DATABASE_UNAVAILABLE", "evaluation_id": evaluation_id}
        with self._factory.connect() as conn:
            if not _table_exists(conn, "capital_efficiency_evaluations"):
                return {"mock_data": False, "status": "MISSING_TABLES", "evaluation_id": evaluation_id}
            row = _fetchone(conn, "SELECT * FROM capital_efficiency_evaluations WHERE evaluation_id=%s", (evaluation_id,))
            if not row:
                return {"mock_data": False, "status": "NOT_FOUND", "evaluation_id": evaluation_id}
            sources = _fetchall(conn, "SELECT * FROM capital_efficiency_sources WHERE evaluation_id=%s ORDER BY linked_at,id", (evaluation_id,))
            related = _related_subject(conn, row)
        refs = _dict(row.get("source_refs_json"))
        return _json_safe(
            {
                "mock_data": False,
                "status": "OK",
                "generated_at": datetime.now(UTC).isoformat(),
                "evaluation": row,
                "sources": sources,
                "related_subject": related,
                "payout_odds_link": refs.get("payout_odds_evaluation_id"),
                "exit_hold_link": refs.get("exit_hold_evaluation_id"),
                "forensics_link": f"/dashboard/api/v2/paper/trade-forensics/{row.get('paper_position_id')}" if row.get("paper_position_id") else None,
            }
        )

    def latest_for_subject(self, conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
        if not _table_exists(conn, "capital_efficiency_evaluations"):
            return None
        return _fetchone(
            conn,
            """
            SELECT * FROM capital_efficiency_evaluations
            WHERE subject_type=%s AND subject_id=%s
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (subject_type, subject_id),
        )

    def observational_summary_for_market(self, conn: Any, *, market_id: str | None = None, position_id: str | None = None, limit: int = 5) -> dict[str, Any]:
        if not _table_exists(conn, "capital_efficiency_evaluations"):
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
        rows = _fetchall(conn, f"SELECT evaluation_id,subject_type,subject_id,market_id,side,capital_locked,reward_per_dollar_hour,capital_efficiency_score,recommendation,reason,missing_inputs_json,created_at FROM capital_efficiency_evaluations WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s", tuple(params))
        return _json_safe({"status": "OK", "latest_evaluations": rows, "observational_only": True})

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

    def _evaluate_record(self, conn: Any, record: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
        account = _account(conn, self._account_id)
        payout = _latest_payout(conn, subject_type=record["subject_type"], subject_id=record["subject_id"])
        exit_hold = _latest_exit_hold(conn, subject_type=record["subject_type"], subject_id=record["subject_id"])
        trade_thesis = TradeThesisEngine(connection_factory=self._factory).latest_for_subject(conn, subject_type=record["subject_type"], subject_id=record["subject_id"])
        active_lock = _active_lock(conn, record.get("paper_position_id")) if record["subject_type"] == "PAPER_POSITION" else None
        values, missing = _metrics(record, account, payout, exit_hold, active_lock, trade_thesis)
        score = _score(values, missing)
        recommendation, reason = _recommendation(values, missing, score)
        evaluation = {
            "evaluation_id": _evaluation_id(record, payout, exit_hold, trade_thesis, recommendation),
            "subject_type": record["subject_type"],
            "subject_id": record["subject_id"],
            "paper_position_id": record.get("paper_position_id"),
            "market_id": record.get("market_id") or (payout or {}).get("market_id") or (exit_hold or {}).get("market_id"),
            "condition_id": record.get("condition_id") or (payout or {}).get("condition_id") or (exit_hold or {}).get("condition_id"),
            "side": record.get("side") or (payout or {}).get("side") or (exit_hold or {}).get("side"),
            "token_id": record.get("token_id") or (payout or {}).get("token_id") or (exit_hold or {}).get("token_id"),
            "capital_efficiency_score": score,
            "recommendation": recommendation,
            "confidence": None,
            "reason": reason,
            "missing_inputs_json": sorted(set(missing)),
            "source_refs_json": {
                "paper_account_id": (account or {}).get("account_id"),
                "payout_odds_evaluation_id": (payout or {}).get("evaluation_id"),
                "exit_hold_evaluation_id": (exit_hold or {}).get("evaluation_id"),
                "trade_thesis_id": (trade_thesis or {}).get("thesis_id"),
            },
            "metadata_json": {
                "observational_only": True,
                "no_trading_mutation": True,
                "no_opportunity_cost_fabricated": True,
                "trade_thesis_trace": _trade_thesis_trace(trade_thesis, values),
            },
            **values,
        }
        if not dry_run:
            _upsert(conn, evaluation, _sources(record, account, payout, exit_hold, active_lock, trade_thesis))
        return _json_safe({"evaluation_id": evaluation["evaluation_id"], "subject_type": record["subject_type"], "subject_id": record["subject_id"], "recommendation": recommendation, "reason": reason, "dry_run": dry_run})


def _position_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_positions"):
        return []
    where = "WHERE pp.id::text=%s" if subject_id else "WHERE pp.current_status IN ('OPEN','EXIT_PENDING') AND pp.closed_at IS NULL AND COALESCE(pp.excluded_from_active_paper_truth,false)=false"
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(conn, f"SELECT 'PAPER_POSITION' AS subject_type, pp.id::text AS subject_id, pp.id::text AS paper_position_id, pp.market_id, pp.intended_outcome AS side, pp.avg_entry AS entry_price, pp.size AS quantity, pp.opened_at, mv.condition_id FROM paper_positions pp LEFT JOIN markets_v2 mv ON mv.market_id=pp.market_id {where} ORDER BY pp.opened_at DESC NULLS LAST LIMIT %s", tuple(params))


def _intent_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_intents"):
        return []
    where = "WHERE paper_intent_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(conn, f"SELECT 'PAPER_INTENT' AS subject_type, paper_intent_id AS subject_id, market_id, side, intended_price AS entry_price, evidence, created_at AS opened_at FROM paper_intents {where} ORDER BY created_at DESC,id DESC LIMIT %s", tuple(params))
    for row in rows:
        evidence = _dict(row.get("evidence"))
        row["quantity"] = _decimal_or_none(evidence.get("quantity"))
    return rows


def _candidate_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return []
    where = "WHERE eligibility_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    rows = _fetchall(conn, f"SELECT 'PAPER_CANDIDATE' AS subject_type, eligibility_id AS subject_id, market_id, side, evidence, updated_at AS opened_at FROM paper_eligibility_candidates {where} ORDER BY updated_at DESC,id DESC LIMIT %s", tuple(params))
    for row in rows:
        evidence = _dict(row.get("evidence"))
        row["entry_price"] = _decimal_or_none(evidence.get("orderbook_best_ask") or _dict(evidence.get("source_evidence")).get("orderbook_best_ask"))
        row["quantity"] = _decimal_or_none(evidence.get("quantity"))
    return rows


def _fresh_seed_records(conn: Any, *, limit: int, subject_id: str | None = None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "fresh_candidate_seeds"):
        return []
    where = "WHERE seed_id=%s" if subject_id else ""
    params: list[Any] = [subject_id] if subject_id else []
    params.append(limit)
    return _fetchall(conn, f"SELECT 'FRESH_SEED' AS subject_type, seed_id AS subject_id, market_id, condition_id, side, expected_token_id AS token_id, created_at AS opened_at, metadata_json FROM fresh_candidate_seeds {where} ORDER BY created_at DESC,id DESC LIMIT %s", tuple(params))


def _account(conn: Any, account_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "paper_accounts"):
        return None
    return _fetchone(conn, "SELECT * FROM paper_accounts WHERE account_id=%s", (account_id,))


def _latest_payout(conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "payout_odds_evaluations"):
        return None
    aliases = _subject_aliases(subject_id)
    return _fetchone(conn, "SELECT * FROM payout_odds_evaluations WHERE subject_type=%s AND subject_id = ANY(%s) ORDER BY created_at DESC,id DESC LIMIT 1", (subject_type, aliases))


def _latest_exit_hold(conn: Any, *, subject_type: str, subject_id: str) -> dict[str, Any] | None:
    if not _table_exists(conn, "exit_hold_evaluations"):
        return None
    mapped = "PAPER_CANDIDATE" if subject_type == "PAPER_CANDIDATE" else subject_type
    if mapped not in {"PAPER_POSITION", "PAPER_CANDIDATE", "PAPER_INTENT"}:
        return None
    aliases = _subject_aliases(subject_id)
    return _fetchone(conn, "SELECT * FROM exit_hold_evaluations WHERE subject_type=%s AND subject_id = ANY(%s) ORDER BY created_at DESC,id DESC LIMIT 1", (mapped, aliases))


def _active_lock(conn: Any, position_id: Any) -> dict[str, Any] | None:
    if not position_id or not _table_exists(conn, "paper_capital_ledger"):
        return None
    row = _fetchone(
        conn,
        """
        SELECT
          COALESCE(SUM(CASE
            WHEN event_type IN ('CAPITAL_LOCKED_ON_FILL','CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL') THEN amount
            WHEN event_type IN ('CAPITAL_RELEASED_ON_CLOSE','CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE') THEN -amount
            ELSE 0 END),0) AS active_lock,
          MIN(created_at) FILTER (WHERE event_type IN ('CAPITAL_LOCKED_ON_FILL','CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL')) AS locked_at,
          MAX(ledger_id) FILTER (WHERE event_type IN ('CAPITAL_LOCKED_ON_FILL','CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL')) AS lock_ledger_id
        FROM paper_capital_ledger
        WHERE paper_position_id=%s
        """,
        (str(position_id),),
    )
    return row


def _subject_aliases(subject_id: str) -> list[str]:
    raw = str(subject_id)
    aliases = [raw]
    prefix = "eligibility_exit_candidate_"
    while raw.startswith(prefix):
        raw = raw[len(prefix) :]
        if raw not in aliases:
            aliases.append(raw)
    return aliases


def _metrics(record: dict[str, Any], account: dict[str, Any] | None, payout: dict[str, Any] | None, exit_hold: dict[str, Any] | None, lock: dict[str, Any] | None, trade_thesis: dict[str, Any] | None = None) -> tuple[dict[str, Any], list[str]]:
    missing: list[str] = []
    if not account:
        missing.append("PAPER_ACCOUNT_MISSING")
    if not payout:
        missing.append("PAYOUT_ODDS_MISSING")
    if not exit_hold and record["subject_type"] != "FRESH_SEED":
        missing.append("EXIT_HOLD_MISSING")
    capital_locked = _decimal_or_none((lock or {}).get("active_lock")) if record["subject_type"] == "PAPER_POSITION" else None
    if capital_locked is None:
        capital_locked = _decimal_or_none((payout or {}).get("stake_usd"))
    if capital_locked is None or capital_locked <= 0:
        missing.append("CAPITAL_LOCKED_MISSING")
    opened_at = (lock or {}).get("locked_at") or record.get("opened_at")
    time_locked = None
    if opened_at and record["subject_type"] == "PAPER_POSITION":
        if getattr(opened_at, "tzinfo", None) is None:
            opened_at = opened_at.replace(tzinfo=UTC)
        time_locked = max(0, int((datetime.now(UTC) - opened_at).total_seconds()))
    elif record["subject_type"] == "PAPER_POSITION":
        missing.append("TIME_LOCKED_MISSING")
    ttr = _int_or_none((exit_hold or {}).get("time_to_resolution_seconds"))
    if ttr is None:
        missing.append("TIME_TO_RESOLUTION_MISSING")
    potential_reward = _decimal_or_none((exit_hold or {}).get("hold_to_resolution_profit_if_win")) or _decimal_or_none((payout or {}).get("profit_if_win"))
    if potential_reward is None:
        missing.append("POTENTIAL_REWARD_MISSING")
    risk_amount = _decimal_or_none((exit_hold or {}).get("hold_to_resolution_max_loss")) or _decimal_or_none((payout or {}).get("max_loss"))
    current_exit_pnl = _decimal_or_none((exit_hold or {}).get("exit_now_pnl"))
    available = _decimal_or_none((account or {}).get("available_balance"))
    exposure = _decimal_or_none((account or {}).get("open_exposure"))
    resolution_hours = Decimal(ttr) / Decimal(3600) if ttr is not None else None
    thesis_hours = _valid_thesis_hold_hours(trade_thesis)
    hold_time_source = "MARKET_RESOLUTION"
    dynamic_hold_time_applied = False
    if thesis_hours is not None:
        hours = thesis_hours
        hold_time_source = str((trade_thesis or {}).get("hold_time_source") or "TRADE_THESIS")
        dynamic_hold_time_applied = True
    else:
        hours = resolution_hours
    safe_hours = max(hours, MIN_HOURS) if hours is not None else None
    reward_per_locked = _divide(potential_reward, capital_locked)
    reward_per_hour = _divide(potential_reward, safe_hours)
    reward_per_dollar_hour = _divide(potential_reward, capital_locked * safe_hours if capital_locked is not None and safe_hours is not None else None)
    resolution_safe_hours = max(resolution_hours, MIN_HOURS) if resolution_hours is not None else None
    original_reward_per_dollar_hour = _divide(potential_reward, capital_locked * resolution_safe_hours if capital_locked is not None and resolution_safe_hours is not None else None)
    current_return = _divide(current_exit_pnl, capital_locked)
    hold_return = _divide(potential_reward, capital_locked)
    return {
        "capital_locked": capital_locked,
        "time_locked_seconds": time_locked,
        "time_to_resolution_seconds": ttr,
        "current_exit_pnl": current_exit_pnl,
        "potential_reward": potential_reward,
        "risk_amount": risk_amount,
        "reward_per_locked_dollar": reward_per_locked,
        "reward_per_hour": reward_per_hour,
        "reward_per_dollar_hour": reward_per_dollar_hour,
        "current_return_pct": current_return,
        "hold_return_pct": hold_return,
        "open_exposure": exposure,
        "available_balance": available,
        "liquidity_exit_quality": str((exit_hold or {}).get("liquidity_exit_quality") or "EXIT_LIQUIDITY_UNKNOWN"),
        "rules_risk": str((exit_hold or {}).get("rules_risk") or "RULES_RISK_UNKNOWN"),
        "risk_of_reversal": str((exit_hold or {}).get("risk_of_reversal") or "UNKNOWN"),
        "_dynamic_hold_time_applied": dynamic_hold_time_applied,
        "_hold_time_source": hold_time_source,
        "_original_resolution_hold_time_hours": resolution_hours,
        "_thesis_expected_hold_time_hours": thesis_hours,
        "_original_reward_per_dollar_hour": original_reward_per_dollar_hour,
    }, missing


def _score(v: dict[str, Any], missing: list[str]) -> Decimal | None:
    if "CAPITAL_LOCKED_MISSING" in missing or "POTENTIAL_REWARD_MISSING" in missing:
        return None
    rpdhr = _decimal_or_none(v.get("reward_per_dollar_hour"))
    base = Decimal("0.50")
    if rpdhr is None:
        base -= Decimal("0.15")
    elif rpdhr >= Decimal("0.10"):
        base += Decimal("0.30")
    elif rpdhr >= Decimal("0.01"):
        base += Decimal("0.15")
    else:
        base -= Decimal("0.10")
    if v.get("liquidity_exit_quality") == "GOOD":
        base += Decimal("0.10")
    elif v.get("liquidity_exit_quality") in {"POOR", "EXIT_LIQUIDITY_UNKNOWN"}:
        base -= Decimal("0.15")
    if v.get("rules_risk") == "HIGH" or v.get("risk_of_reversal") == "HIGH":
        base -= Decimal("0.20")
    elif v.get("rules_risk") == "RULES_RISK_UNKNOWN":
        base -= Decimal("0.05")
    if "TIME_TO_RESOLUTION_MISSING" in missing:
        base -= Decimal("0.10")
    return min(Decimal("1.0"), max(Decimal("0.0"), base.quantize(Decimal("0.0001"))))


def _valid_thesis_hold_hours(trade_thesis: dict[str, Any] | None) -> Decimal | None:
    if not trade_thesis:
        return None
    if str(trade_thesis.get("status") or "").upper() != "THESIS_SUPPORTED":
        return None
    if str(trade_thesis.get("exit_intent") or "").upper() in {"", "UNKNOWN_EXIT"}:
        return None
    hours = _decimal_or_none(trade_thesis.get("expected_hold_time_hours"))
    if hours is None or hours <= 0:
        return None
    return hours


def _trade_thesis_trace(trade_thesis: dict[str, Any] | None, values: dict[str, Any]) -> dict[str, Any]:
    if not trade_thesis:
        return {
            "status": "THESIS_MISSING",
            "dynamic_hold_time_applied": False,
            "hold_time_reason": "No supported trade thesis evaluation was available.",
        }
    original = _decimal_or_none(values.get("_original_reward_per_dollar_hour"))
    dynamic = _decimal_or_none(values.get("reward_per_dollar_hour"))
    return _json_safe(
        {
            "thesis_id": trade_thesis.get("thesis_id"),
            "trade_thesis_type": trade_thesis.get("trade_thesis_type"),
            "exit_intent": trade_thesis.get("exit_intent"),
            "status": trade_thesis.get("status"),
            "blocker_code": trade_thesis.get("blocker_code"),
            "hold_time_source": values.get("_hold_time_source"),
            "original_resolution_hold_time_hours": values.get("_original_resolution_hold_time_hours"),
            "thesis_expected_hold_time_hours": values.get("_thesis_expected_hold_time_hours"),
            "hold_time_used_hours": values.get("_thesis_expected_hold_time_hours") or values.get("_original_resolution_hold_time_hours"),
            "dynamic_hold_time_applied": bool(values.get("_dynamic_hold_time_applied")),
            "original_reward_per_dollar_hour": original,
            "dynamic_reward_per_dollar_hour": dynamic,
            "reward_per_dollar_hour_delta": (dynamic - original) if dynamic is not None and original is not None else None,
            "capital_efficiency_before_thesis": None,
            "capital_efficiency_after_thesis": None,
            "required_to_pass": trade_thesis.get("required_to_pass_json") or [],
        }
    )


def _recommendation(v: dict[str, Any], missing: list[str], score: Decimal | None) -> tuple[str, str]:
    if {"CAPITAL_LOCKED_MISSING", "POTENTIAL_REWARD_MISSING"} & set(missing):
        return "CAPITAL_INSUFFICIENT_DATA", "Missing locked capital or potential reward; capital efficiency cannot be safely evaluated."
    current_return = _decimal_or_none(v.get("current_return_pct")) or Decimal("0")
    hold_return = _decimal_or_none(v.get("hold_return_pct")) or Decimal("0")
    hold_extra = hold_return - current_return
    rpdhr = _decimal_or_none(v.get("reward_per_dollar_hour"))
    risk_high = v.get("rules_risk") == "HIGH" or v.get("risk_of_reversal") == "HIGH"
    liquidity = v.get("liquidity_exit_quality")
    if current_return > 0 and hold_extra <= Decimal("0.25") and (risk_high or (v.get("time_to_resolution_seconds") or 0) > 7 * 24 * 3600):
        return "CAPITAL_RELEASE_REVIEW", "Exit profit is available and remaining hold efficiency is weak relative to risk or time."
    if risk_high and current_return > 0 and liquidity in {"GOOD", "FAIR"}:
        return "CAPITAL_REDUCE_REVIEW", "Capital efficiency is under review because risk is rising while exit liquidity exists."
    if liquidity == "POOR":
        return "CAPITAL_BLOCK", "Exit liquidity is poor; capital lock is not efficient enough for support."
    if "TIME_TO_RESOLUTION_MISSING" in missing or liquidity == "EXIT_LIQUIDITY_UNKNOWN" or v.get("rules_risk") == "RULES_RISK_UNKNOWN":
        return "CAPITAL_WATCH", "Capital efficiency is partially evaluated; missing time, rules, or liquidity evidence requires watch."
    if score is not None and score >= Decimal("0.70") and rpdhr is not None and not risk_high:
        return "CAPITAL_SUPPORT", "Capital lock is efficient relative to reward, time, liquidity, and risk evidence."
    if score is not None and score < Decimal("0.30"):
        return "CAPITAL_BLOCK", "Capital efficiency score is weak from source-backed reward, time, liquidity, and risk inputs."
    return "CAPITAL_WATCH", "Capital efficiency is acceptable for observation but not strong enough for support."


def _sources(record: dict[str, Any], account: dict[str, Any] | None, payout: dict[str, Any] | None, exit_hold: dict[str, Any] | None, lock: dict[str, Any] | None, trade_thesis: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    sources = [{"source_table": _source_table(record["subject_type"]), "source_record_id": record["subject_id"], "source_type": record["subject_type"], "contribution_summary": "subject source for capital efficiency"}]
    if account:
        sources.append({"source_table": "paper_accounts", "source_record_id": account["account_id"], "source_type": "PAPER_ACCOUNT", "contribution_summary": "available balance and exposure source"})
    if payout:
        sources.append({"source_table": "payout_odds_evaluations", "source_record_id": payout["evaluation_id"], "source_type": "PAYOUT_ODDS", "contribution_summary": "potential reward and risk source"})
    if exit_hold:
        sources.append({"source_table": "exit_hold_evaluations", "source_record_id": exit_hold["evaluation_id"], "source_type": "EXIT_HOLD", "contribution_summary": "exit value, time, liquidity, and risk source"})
    if trade_thesis:
        sources.append({"source_table": "trade_thesis_evaluations", "source_record_id": trade_thesis["thesis_id"], "source_type": "TRADE_THESIS", "contribution_summary": "trade thesis, exit intent, and dynamic hold-time source"})
    if lock and lock.get("lock_ledger_id"):
        sources.append({"source_table": "paper_capital_ledger", "source_record_id": str(lock["lock_ledger_id"]), "source_type": "CAPITAL_LOCK", "contribution_summary": "active locked notional source"})
    return sources


def _upsert(conn: Any, ev: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    conn.execute(
        """
        INSERT INTO capital_efficiency_evaluations (
            evaluation_id, subject_type, subject_id, paper_position_id, market_id, condition_id, side, token_id,
            capital_locked, time_locked_seconds, time_to_resolution_seconds, current_exit_pnl, potential_reward, risk_amount,
            reward_per_locked_dollar, reward_per_hour, reward_per_dollar_hour, current_return_pct, hold_return_pct,
            open_exposure, available_balance, liquidity_exit_quality, rules_risk, risk_of_reversal, capital_efficiency_score,
            recommendation, confidence, reason, missing_inputs_json, source_refs_json, metadata_json
        ) VALUES (
            %(evaluation_id)s,%(subject_type)s,%(subject_id)s,%(paper_position_id)s,%(market_id)s,%(condition_id)s,%(side)s,%(token_id)s,
            %(capital_locked)s,%(time_locked_seconds)s,%(time_to_resolution_seconds)s,%(current_exit_pnl)s,%(potential_reward)s,%(risk_amount)s,
            %(reward_per_locked_dollar)s,%(reward_per_hour)s,%(reward_per_dollar_hour)s,%(current_return_pct)s,%(hold_return_pct)s,
            %(open_exposure)s,%(available_balance)s,%(liquidity_exit_quality)s,%(rules_risk)s,%(risk_of_reversal)s,%(capital_efficiency_score)s,
            %(recommendation)s,%(confidence)s,%(reason)s,%(missing_inputs_json)s,%(source_refs_json)s,%(metadata_json)s
        )
        ON CONFLICT (evaluation_id) DO UPDATE SET updated_at=now()
        """,
        {**ev, "missing_inputs_json": Jsonb(ev["missing_inputs_json"]), "source_refs_json": Jsonb(ev["source_refs_json"]), "metadata_json": Jsonb(ev["metadata_json"])},
    )
    for source in sources:
        conn.execute("INSERT INTO capital_efficiency_sources (evaluation_id,source_table,source_record_id,source_type,contribution_summary) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (ev["evaluation_id"], source["source_table"], str(source["source_record_id"]), source["source_type"], source["contribution_summary"]))


def _evaluation_id(record: dict[str, Any], payout: dict[str, Any] | None, exit_hold: dict[str, Any] | None, trade_thesis: dict[str, Any] | None, recommendation: str) -> str:
    raw = "|".join([record["subject_type"], record["subject_id"], str((payout or {}).get("evaluation_id") or ""), str((exit_hold or {}).get("evaluation_id") or ""), str((trade_thesis or {}).get("thesis_id") or ""), recommendation])
    return f"capital_efficiency_{uuid5(NAMESPACE_URL, raw).hex}"


def _latest_rows(conn: Any, where: str, limit: int) -> list[dict[str, Any]]:
    return _fetchall(conn, f"SELECT evaluation_id,subject_type,subject_id,paper_position_id,market_id,side,capital_locked,time_to_resolution_seconds,potential_reward,reward_per_dollar_hour,capital_efficiency_score,recommendation,reason,missing_inputs_json,created_at FROM capital_efficiency_evaluations WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s", (limit,))


def _related_subject(conn: Any, row: dict[str, Any]) -> dict[str, Any] | None:
    table = _source_table(row["subject_type"])
    key = {"PAPER_POSITION": "id::text", "PAPER_INTENT": "paper_intent_id", "PAPER_CANDIDATE": "eligibility_id", "FRESH_SEED": "seed_id"}[row["subject_type"]]
    if not _table_exists(conn, table):
        return None
    return _fetchone(conn, f"SELECT * FROM {table} WHERE {key}=%s", (row["subject_id"],))


def _source_table(subject_type: str) -> str:
    return {"PAPER_POSITION": "paper_positions", "PAPER_INTENT": "paper_intents", "PAPER_CANDIDATE": "paper_eligibility_candidates", "FRESH_SEED": "fresh_candidate_seeds"}[subject_type]


def _tables_ready(conn: Any) -> bool:
    return _table_exists(conn, "capital_efficiency_evaluations") and _table_exists(conn, "capital_efficiency_sources")


def _empty_dashboard(status: str, generated_at: str) -> dict[str, Any]:
    return {"mock_data": False, "status": status, "generated_at": generated_at, "security_governance_status": SECURITY_GOVERNANCE_STATUS, "total_evaluations": 0, "latest_evaluations": []}


def _safety_counts(conn: Any) -> dict[str, Any]:
    counts = {table: _count_table(conn, table) for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "paper_position_closes", "paper_capital_ledger", "live_orders", "orders_v2", "fills_v2", "positions")}
    account = _fetchone(conn, "SELECT current_balance,available_balance,locked_balance,open_exposure,realized_pnl,unrealized_pnl FROM paper_accounts WHERE account_id='paper_default'") if _table_exists(conn, "paper_accounts") else None
    counts["capital_balances"] = _json_safe(account) if account else None
    return counts


def _trading_mutation(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return before != after


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


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _divide(a: Any, b: Any) -> Decimal | None:
    left = _decimal_or_none(a)
    right = _decimal_or_none(b)
    if left is None or right is None or right == 0:
        return None
    return left / right


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    return int(value or 0)


def _float(value: Any) -> float:
    return float(value or 0)


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
