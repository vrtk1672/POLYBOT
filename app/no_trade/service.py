from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg import Connection

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.no_trade.candidate_tracker import NoTradeCandidateTracker
from app.no_trade.contracts import NoTradeDecision
from app.no_trade.memory_updater import NoTradeMemoryUpdater
from app.no_trade.no_trade_errors import NoTradeValidationError
from app.no_trade.no_trade_logger import NoTradeLogger
from app.no_trade.post_fact_reviewer import NoTradePostFactReviewer
from app.no_trade.regret_scorer import NoTradeRegretScorer
from app.repositories.no_trade_log_repository import NoTradeLogRepository
from app.repositories.no_trade_post_fact_review_repository import NoTradePostFactReviewRepository
from app.repositories.no_trade_reason_repository import NoTradeReasonRepository
from app.repositories.no_trade_regret_score_repository import NoTradeRegretScoreRepository


class NoTradeService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self.tracker = NoTradeCandidateTracker()
        self.logger = NoTradeLogger(self.tracker)
        self.reviewer = NoTradePostFactReviewer()
        self.regret_scorer = NoTradeRegretScorer()
        self.memory_updater = NoTradeMemoryUpdater()
        self.logs = NoTradeLogRepository()
        self.reasons = NoTradeReasonRepository()
        self.reviews = NoTradePostFactReviewRepository()
        self.regrets = NoTradeRegretScoreRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                if not _exists(conn, "no_trade_log"):
                    return _empty("EMPTY")
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS logged_today,
                      COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_data_count,
                      MAX(created_at) AS latest_log_ts
                    FROM no_trade_log
                    """
                ).fetchone()
                reviews = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS reviews_today FROM no_trade_post_fact_review").fetchone()
                regrets = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND regret_band='HIGH_REGRET') AS high_regret_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND regret_band='GOOD_NO_TRADE') AS good_no_trade_today
                    FROM no_trade_regret_score
                    """
                ).fetchone()
            return {
                "status": "HEALTHY",
                "logged_today": int((stats or {}).get("logged_today") or 0),
                "reviews_today": int((reviews or {}).get("reviews_today") or 0),
                "high_regret_today": int((regrets or {}).get("high_regret_today") or 0),
                "good_no_trade_today": int((regrets or {}).get("good_no_trade_today") or 0),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
                "latest_log_ts": _serialize((stats or {}).get("latest_log_ts")),
                "errors_today": 0,
            }
        except Exception as exc:
            return {**_empty("ERROR"), "error": str(exc)}

    def log_decision(self, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        decision = self.logger.build(payload)
        if not decision.market_id:
            raise NoTradeValidationError("market_id is required")
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json"), "reasons": [reason.model_dump(mode="json") for reason in decision.reasons]}
        with self._factory.connect() as conn:
            with conn.transaction():
                row = self.logs.insert(conn, decision)
                duplicate = row["no_trade_id"] != decision.no_trade_id
                reason_rows = [] if duplicate else self.reasons.insert_many(conn, decision.no_trade_id, decision.reasons)
            conn.commit()
        event = EventType.NO_TRADE_INSUFFICIENT_DATA.value if decision.insufficient_data else EventType.NO_TRADE_LOGGED.value
        self._publish(event, {"no_trade_id": row["no_trade_id"], "market_id": decision.market_id, "source_layer": decision.source_layer, "primary_reason": decision.primary_reason})
        if not duplicate:
            for reason in decision.reasons:
                self._publish(EventType.NO_TRADE_REASON_CREATED.value, {"no_trade_id": decision.no_trade_id, "market_id": decision.market_id, "reason": reason.reason, "severity": reason.severity})
        return {"dry_run": False, "written": not duplicate, "deduped": duplicate, "decision": _serialize(row), "reasons": _serialize(reason_rows)}

    def review(self, *, no_trade_id: str, dry_run: bool = False, review_horizon_seconds: int = 0, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._factory.connect() as conn:
            row = self.logs.by_id(conn, no_trade_id)
            if not row:
                raise ValueError(f"no-trade log not found: {no_trade_id}")
            reason_rows = self.reasons.by_no_trade_id(conn, no_trade_id)
        decision = _decision_from_row(row, reason_rows)
        review = self.reviewer.review(decision=decision, evidence=evidence, review_horizon_seconds=review_horizon_seconds)
        regret = self.regret_scorer.score(decision=decision, review=review)
        regret.update_memory = self.memory_updater.should_update(regret)
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "review": review.model_dump(mode="json"), "regret": regret.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                review_row = self.reviews.insert(conn, review)
                regret_row = self.regrets.insert(conn, regret)
            conn.commit()
        self._publish(EventType.NO_TRADE_POST_FACT_REVIEW_CREATED.value, {"no_trade_id": no_trade_id, "market_id": decision.market_id, "review_status": review.review_status})
        self._publish(EventType.NO_TRADE_REGRET_SCORED.value, {"no_trade_id": no_trade_id, "market_id": decision.market_id, "regret_band": regret.regret_band})
        if regret.regret_band == "HIGH_REGRET":
            self._publish(EventType.NO_TRADE_HIGH_REGRET.value, {"no_trade_id": no_trade_id, "market_id": decision.market_id})
        if regret.regret_band == "GOOD_NO_TRADE":
            self._publish(EventType.NO_TRADE_GOOD_DECISION.value, {"no_trade_id": no_trade_id, "market_id": decision.market_id})
        if regret.update_memory:
            self._publish(EventType.NO_TRADE_CANONICAL_MEMORY_UPDATED.value, {"no_trade_id": no_trade_id, "market_id": decision.market_id, "learning_signal": regret.learning_signal})
        return {"dry_run": False, "written": True, "review": _serialize(review_row), "regret": _serialize(regret_row)}

    def rebuild(self, *, dry_run: bool = False, source_layer: str | None = None, market_id: str | None = None) -> dict[str, Any]:
        candidates = self._backfill_candidates(source_layer=source_layer, market_id=market_id)
        if dry_run:
            return {"dry_run": True, "written": False, "candidate_count": len(candidates), "candidates": candidates[:25]}
        written = 0
        deduped = 0
        for candidate in candidates:
            result = self.log_decision(candidate, dry_run=False)
            if result.get("deduped"):
                deduped += 1
            elif result.get("written"):
                written += 1
        return {"dry_run": False, "written": True, "candidate_count": len(candidates), "rows_written": written, "deduped": deduped}

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.logs.recent(conn, limit=limit)]

    def detail(self, no_trade_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            row = self.logs.by_id(conn, no_trade_id)
            if not row:
                raise ValueError(f"no-trade log not found: {no_trade_id}")
            return {
                "log": _serialize(row),
                "reasons": _serialize(self.reasons.by_no_trade_id(conn, no_trade_id)),
                "reviews": _serialize(self.reviews.by_no_trade_id(conn, no_trade_id)),
                "regret_scores": _serialize(self.regrets.by_no_trade_id(conn, no_trade_id)),
            }

    def top_reasons(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return _serialize(self.reasons.top(conn, limit=limit))

    def by_engine(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return _serialize(conn.execute("SELECT COALESCE(candidate_engine,'UNKNOWN') AS candidate_engine, COUNT(*) AS count FROM no_trade_log GROUP BY COALESCE(candidate_engine,'UNKNOWN') ORDER BY count DESC").fetchall())

    def by_market_family(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return _serialize(conn.execute("SELECT COALESCE(market_family,'UNKNOWN') AS market_family, COUNT(*) AS count FROM no_trade_log GROUP BY COALESCE(market_family,'UNKNOWN') ORDER BY count DESC").fetchall())

    def regret_summary(self) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.regrets.summary(conn))

    def pending_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return _serialize(self.reviews.pending(conn, limit=limit))

    def _backfill_candidates(self, *, source_layer: str | None, market_id: str | None) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        candidates: list[dict[str, Any]] = []
        with self._factory.connect() as conn:
            if source_layer in {None, "strategy"} and _exists(conn, "strategy_routes_v2"):
                candidates.extend(_strategy_candidates(conn, market_id))
            if source_layer in {None, "capital"} and _exists(conn, "capital_allocations_v2"):
                candidates.extend(_capital_candidates(conn, market_id))
            if source_layer in {None, "risk"} and _exists(conn, "risk_gate_decisions"):
                candidates.extend(_risk_candidates(conn, market_id))
            if source_layer in {None, "execution"} and _exists(conn, "execution_errors"):
                candidates.extend(_execution_candidates(conn, market_id))
            if source_layer in {None, "exit"} and _exists(conn, "exit_failures"):
                candidates.extend(_exit_candidates(conn, market_id))
            if source_layer in {None, "opportunity"} and _exists(conn, "opportunity_scores_v2"):
                candidates.extend(_opportunity_candidates(conn, market_id))
        return candidates

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, "no_trade_intelligence", aggregate_type="no_trade", aggregate_id=str(payload.get("no_trade_id") or payload.get("market_id") or "no_trade"))
        except Exception:
            return


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "logged_today": 0, "reviews_today": 0, "high_regret_today": 0, "good_no_trade_today": 0, "insufficient_data_count": 0, "latest_log_ts": None, "errors_today": 0}


def _exists(conn: Connection, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table,)).fetchone()["exists"])


def _serialize(value: Any) -> Any:
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decision_from_row(row: dict[str, Any], reason_rows: list[dict[str, Any]]) -> NoTradeDecision:
    payload = dict(row)
    payload["reasons"] = [reason["reason"] for reason in reason_rows] or [row["primary_reason"]]
    return NoTradeCandidateTracker().build_decision(payload)


def _strategy_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, run_id, market_id, market_family, side, selected_engine, route_status,
               opportunity_score, no_trade_reasons_json, risk_flags_json, route_reason
        FROM strategy_routes_v2
        WHERE route_status IN ('NO_TRADE','BLOCKED','INSUFFICIENT_DATA','WATCHLIST')
          AND (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row["market_id"],
            "market_family": row.get("market_family"),
            "side": row.get("side"),
            "candidate_engine": row.get("selected_engine"),
            "source_layer": "strategy",
            "source_run_id": row.get("run_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "NO_TRADE" if row.get("route_status") == "NO_TRADE" else "BLOCKED",
            "primary_reason": (row.get("no_trade_reasons_json") or ["strategy_block"])[0] if isinstance(row.get("no_trade_reasons_json"), list) and row.get("no_trade_reasons_json") else row.get("route_status", "strategy_block"),
            "reasons": row.get("no_trade_reasons_json") or [row.get("route_status") or "strategy_block"],
            "risk_flags": row.get("risk_flags_json") or [],
            "opportunity_score": row.get("opportunity_score"),
            "strategy_route_status": row.get("route_status"),
            "explanation": row.get("route_reason") or "Backfilled no-trade from strategy route.",
        }
        for row in rows
    ]


def _capital_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, allocation_id, market_id, market_family, side, engine, allocation_status,
               rejection_reason, allocation_reason, approved_size_usd, max_loss_usd
        FROM capital_allocations_v2
        WHERE allocation_status IN ('BLOCKED','INSUFFICIENT_DATA')
          AND (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row["market_id"],
            "market_family": row.get("market_family"),
            "side": row.get("side"),
            "candidate_engine": row.get("engine"),
            "source_layer": "capital",
            "source_run_id": row.get("allocation_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "BLOCKED",
            "primary_reason": row.get("rejection_reason") or "no_capital",
            "reasons": [row.get("rejection_reason") or "no_capital"],
            "capital_allocation_status": row.get("allocation_status"),
            "would_have_size_usd": row.get("approved_size_usd"),
            "would_have_max_loss_usd": row.get("max_loss_usd"),
            "explanation": row.get("allocation_reason") or "Backfilled no-trade from capital allocation block.",
        }
        for row in rows
    ]


def _risk_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, run_id, market_id, market_family, side, engine, decision,
               block_reasons_json, explanation, approved_position_size_usd, approved_max_loss_usd
        FROM risk_gate_decisions
        WHERE blocked IS TRUE OR decision IN ('BLOCKED','COOLDOWN','INSUFFICIENT_DATA')
          AND (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row["market_id"],
            "market_family": row.get("market_family"),
            "side": row.get("side"),
            "candidate_engine": row.get("engine"),
            "source_layer": "risk",
            "source_run_id": row.get("run_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "BLOCKED",
            "primary_reason": (row.get("block_reasons_json") or ["governor_block"])[0] if isinstance(row.get("block_reasons_json"), list) and row.get("block_reasons_json") else "governor_block",
            "reasons": row.get("block_reasons_json") or ["governor_block"],
            "risk_gate_decision": row.get("decision"),
            "would_have_size_usd": row.get("approved_position_size_usd"),
            "would_have_max_loss_usd": row.get("approved_max_loss_usd"),
            "explanation": row.get("explanation") or "Backfilled no-trade from risk gate block.",
        }
        for row in rows
    ]


def _execution_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, error_id, market_id, order_id, error_type, message, severity
        FROM execution_errors
        WHERE (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row.get("market_id") or "unknown",
            "source_layer": "execution",
            "source_run_id": row.get("error_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "BLOCKED",
            "primary_reason": row.get("error_type") or row.get("message") or "execution_block",
            "reasons": [row.get("error_type") or row.get("message") or "execution_block"],
            "execution_block_reason": row.get("message"),
            "explanation": "Backfilled no-trade from execution precheck/block.",
        }
        for row in rows
    ]


def _exit_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, failure_id, market_id, failure_type, reason, severity
        FROM exit_failures
        WHERE (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row.get("market_id") or "unknown",
            "source_layer": "exit",
            "source_run_id": row.get("failure_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "BLOCKED",
            "primary_reason": row.get("reason") or row.get("failure_type") or "bad_exit_quality",
            "reasons": [row.get("reason") or row.get("failure_type") or "bad_exit_quality"],
            "exit_block_reason": row.get("reason"),
            "explanation": "Backfilled no-trade from exit failure.",
        }
        for row in rows
    ]


def _opportunity_candidates(conn: Connection, market_id: str | None) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, run_id, market_id, market_family, side, score_band, opportunity_score,
               candidate_engines_json, no_trade_reasons_json, insufficient_data,
               insufficient_data_reasons_json, explanation
        FROM opportunity_scores_v2
        WHERE score_band='BLOCKED' OR insufficient_data IS TRUE
          AND (%s::text IS NULL OR market_id=%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (market_id, market_id),
    ).fetchall()
    return [
        {
            "market_id": row["market_id"],
            "market_family": row.get("market_family"),
            "side": row.get("side"),
            "candidate_engine": (row.get("candidate_engines_json") or [None])[0] if isinstance(row.get("candidate_engines_json"), list) else None,
            "source_layer": "opportunity",
            "source_run_id": row.get("run_id"),
            "source_record_id": str(row.get("id")),
            "decision_status": "INSUFFICIENT_DATA" if row.get("insufficient_data") else "BLOCKED",
            "primary_reason": (row.get("no_trade_reasons_json") or row.get("insufficient_data_reasons_json") or ["low_edge"])[0],
            "reasons": row.get("no_trade_reasons_json") or row.get("insufficient_data_reasons_json") or ["low_edge"],
            "opportunity_score": row.get("opportunity_score"),
            "insufficient_data": bool(row.get("insufficient_data")),
            "insufficient_data_reasons": row.get("insufficient_data_reasons_json") or [],
            "explanation": row.get("explanation") or "Backfilled no-trade from opportunity score.",
        }
        for row in rows
    ]
