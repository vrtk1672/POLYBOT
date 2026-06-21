from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.learning.ai_learning_builder import AILearningBuilder
from app.learning.engine_learning_builder import EngineLearningBuilder
from app.learning.memory_update_coordinator import MemoryUpdateCoordinator
from app.learning.model_adjustment_recommender import ModelAdjustmentRecommender
from app.learning.no_trade_learning_builder import NoTradeLearningBuilder
from app.learning.signal_performance_analyzer import SignalPerformanceAnalyzer
from app.learning.source_learning_builder import SourceLearningBuilder
from app.learning.trade_reviewer import TradeReviewer
from app.learning.whale_learning_builder import WhaleLearningBuilder
from app.repositories.ai_learning_repository import AILearningRepository
from app.repositories.engine_learning_repository import EngineLearningRepository
from app.repositories.learning_repository_helpers import count_today, recent, row_dict, rows
from app.repositories.model_adjustment_repository import ModelAdjustmentRepository
from app.repositories.no_trade_learning_repository import NoTradeLearningRepository
from app.repositories.signal_performance_repository import SignalPerformanceRepository
from app.repositories.source_learning_repository import SourceLearningRepository
from app.repositories.trade_review_repository import TradeReviewRepository
from app.repositories.whale_learning_repository import WhaleLearningRepository


class LearningService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._trade_reviewer = TradeReviewer()
        self._signal_analyzer = SignalPerformanceAnalyzer()
        self._engine_builder = EngineLearningBuilder()
        self._source_builder = SourceLearningBuilder()
        self._whale_builder = WhaleLearningBuilder()
        self._ai_builder = AILearningBuilder()
        self._no_trade_builder = NoTradeLearningBuilder()
        self._recommender = ModelAdjustmentRecommender()
        self._memory = MemoryUpdateCoordinator()
        self._trade_reviews = TradeReviewRepository()
        self._signals = SignalPerformanceRepository()
        self._engines = EngineLearningRepository()
        self._sources = SourceLearningRepository()
        self._whales = WhaleLearningRepository()
        self._ai = AILearningRepository()
        self._no_trade = NoTradeLearningRepository()
        self._adjustments = ModelAdjustmentRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {
                "status": "DISABLED",
                "trade_reviews_today": 0,
                "pending_reviews": 0,
                "learning_events_today": 0,
                "model_adjustments_pending": 0,
                "insufficient_data_count": 0,
                "latest_review_ts": None,
                "errors_today": 0,
            }
        try:
            with self._factory.connect() as conn:
                if not self._table_exists(conn, "trade_reviews"):
                    return {"status": "EMPTY", "trade_reviews_today": 0, "pending_reviews": 0, "learning_events_today": 0, "model_adjustments_pending": 0, "insufficient_data_count": 0, "latest_review_ts": None, "errors_today": 0}
                pending = conn.execute("SELECT COUNT(*) AS count FROM trade_reviews WHERE review_status='PENDING'").fetchone()
                reviews_today = conn.execute("SELECT COUNT(*) AS count FROM trade_reviews WHERE created_at::date=CURRENT_DATE").fetchone()
                insufficient = conn.execute(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM trade_reviews WHERE insufficient_data IS TRUE) +
                      (SELECT COUNT(*) FROM no_trade_learning WHERE learning_signal='improve_data') AS count
                    """
                ).fetchone()
                adjustments = conn.execute("SELECT COUNT(*) AS count FROM model_adjustments WHERE status IN ('RECOMMENDED','REVIEW_REQUIRED')").fetchone()
                latest = conn.execute("SELECT created_at FROM trade_reviews ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
                learning_events = conn.execute(
                    "SELECT COUNT(*) AS count FROM event_log WHERE event_type LIKE 'learning.%' AND stored_at::date=CURRENT_DATE"
                ).fetchone() if self._table_exists(conn, "event_log") else {"count": 0}
            return {
                "status": "OK",
                "trade_reviews_today": int((reviews_today or {}).get("count") or 0),
                "pending_reviews": int((pending or {}).get("count") or 0),
                "learning_events_today": int((learning_events or {}).get("count") or 0),
                "model_adjustments_pending": int((adjustments or {}).get("count") or 0),
                "insufficient_data_count": int((insufficient or {}).get("count") or 0),
                "latest_review_ts": (row_dict(latest) or {}).get("created_at"),
                "errors_today": 0,
            }
        except Exception as exc:
            return {"status": "ERROR", "errors_today": 1, "error": str(exc)}

    def review_trade(self, payload: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        review = self._trade_reviewer.review(payload)
        engine_learning = self._engine_builder.build_from_review(review)
        signals = [self._signal_analyzer.analyze(signal, market_id=review.market_id, market_family=review.market_family) for signal in payload.get("signals", [])]
        sources = [self._source_builder.build({**source, "market_family": source.get("market_family") or review.market_family}) for source in payload.get("sources", [])]
        whales = [self._whale_builder.build({**whale, "market_id": whale.get("market_id") or review.market_id, "market_family": whale.get("market_family") or review.market_family}) for whale in payload.get("whales", [])]
        ai_items = [self._ai_builder.build({**item, "market_id": item.get("market_id") or review.market_id, "market_family": item.get("market_family") or review.market_family}) for item in payload.get("ai", [])]
        adjustments = [item for item in [self._recommender.from_engine_learning(engine_learning), *(self._recommender.from_signal_performance(signal) for signal in signals)] if item is not None]
        memory_decision = self._memory.evaluate(confidence=engine_learning.confidence, evidence_exists=review.review_status == "REVIEWED", requested=bool(payload.get("update_memory", True)))
        result = {
            "written": False,
            "dry_run": dry_run,
            "review": review.model_dump(mode="json"),
            "engine_learning": engine_learning.model_dump(mode="json"),
            "signal_performance": [signal.model_dump(mode="json") for signal in signals],
            "source_learning": [source.model_dump(mode="json") for source in sources],
            "whale_learning": [whale.model_dump(mode="json") for whale in whales],
            "ai_learning": [item.model_dump(mode="json") for item in ai_items],
            "model_adjustments": [adjustment.model_dump(mode="json") for adjustment in adjustments],
            "memory_update": memory_decision.model_dump(mode="json"),
        }
        if dry_run or not self._factory.enabled:
            return result
        with self._factory.connect() as conn, conn.transaction():
            result["review"] = self._trade_reviews.insert(conn, review)
            result["engine_learning"] = self._engines.insert(conn, engine_learning)
            result["signal_performance"] = [self._signals.insert(conn, signal) for signal in signals]
            result["source_learning"] = [self._sources.insert(conn, source) for source in sources]
            result["whale_learning"] = [self._whales.insert(conn, whale) for whale in whales]
            result["ai_learning"] = [self._ai.insert(conn, item) for item in ai_items]
            result["model_adjustments"] = [self._adjustments.insert(conn, adjustment) for adjustment in adjustments]
        result["written"] = True
        self._publish(EventType.LEARNING_TRADE_REVIEW_CREATED.value, {"review_id": review.review_id, "market_id": review.market_id, "status": review.review_status}, review.review_id)
        self._publish(EventType.LEARNING_ENGINE_UPDATED.value, {"engine": engine_learning.engine, "learning_signal": engine_learning.learning_signal}, engine_learning.engine_learning_id)
        for signal in signals:
            self._publish(EventType.LEARNING_SIGNAL_PERFORMANCE_UPDATED.value, {"signal_perf_id": signal.signal_perf_id, "source_type": signal.source_type, "accuracy_score": signal.accuracy_score}, signal.signal_perf_id)
        for source in sources:
            self._publish(EventType.LEARNING_SOURCE_UPDATED.value, {"source_learning_id": source.source_learning_id, "source_type": source.source_type, "learning_signal": source.learning_signal}, source.source_learning_id)
        for whale in whales:
            self._publish(EventType.LEARNING_WHALE_UPDATED.value, {"whale_learning_id": whale.whale_learning_id, "whale_id": whale.whale_id, "learning_signal": whale.learning_signal}, whale.whale_learning_id)
        for item in ai_items:
            self._publish(EventType.LEARNING_AI_UPDATED.value, {"ai_learning_id": item.ai_learning_id, "model_name": item.model_name, "learning_signal": item.learning_signal}, item.ai_learning_id)
        if memory_decision.update_memory:
            self._publish(EventType.LEARNING_MEMORY_UPDATE_APPLIED.value, {"review_id": review.review_id, "reason": memory_decision.reason}, review.review_id)
        if review.insufficient_data:
            self._publish(EventType.LEARNING_INSUFFICIENT_DATA.value, {"review_id": review.review_id, "reasons": review.insufficient_data_reasons}, review.review_id)
        for adjustment in adjustments:
            self._publish(EventType.LEARNING_MODEL_ADJUSTMENT_RECOMMENDED.value, {"adjustment_id": adjustment.adjustment_id, "target_module": adjustment.target_module, "status": adjustment.status}, adjustment.adjustment_id)
        return result

    def review_no_trade(self, no_trade_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"written": False, "dry_run": dry_run, "reason": "persistence_disabled"}
        with self._factory.connect() as conn:
            log = conn.execute("SELECT * FROM no_trade_log WHERE no_trade_id=%s ORDER BY created_at DESC LIMIT 1", (no_trade_id,)).fetchone()
            regret = conn.execute("SELECT * FROM no_trade_regret_score WHERE no_trade_id=%s ORDER BY created_at DESC LIMIT 1", (no_trade_id,)).fetchone()
        if not log or not regret:
            return {"written": False, "dry_run": dry_run, "status": "INSUFFICIENT_DATA", "reason": "missing_no_trade_regret_evidence", "no_trade_id": no_trade_id}
        learning = self._no_trade_builder.build(row_dict(log) or {}, row_dict(regret) or {})
        adjustment = self._recommender.from_no_trade_learning(learning)
        result = {
            "written": False,
            "dry_run": dry_run,
            "no_trade_learning": learning.model_dump(mode="json"),
            "model_adjustment": adjustment.model_dump(mode="json") if adjustment else None,
        }
        if dry_run:
            return result
        with self._factory.connect() as conn, conn.transaction():
            existing = self._no_trade.by_no_trade_id(conn, no_trade_id)
            if existing:
                result["no_trade_learning"] = existing
            else:
                result["no_trade_learning"] = self._no_trade.insert(conn, learning)
                if adjustment:
                    result["model_adjustment"] = self._adjustments.insert(conn, adjustment)
        result["written"] = True
        self._publish(EventType.LEARNING_NO_TRADE_UPDATED.value, {"no_trade_id": no_trade_id, "learning_signal": learning.learning_signal}, learning.no_trade_learning_id)
        return result

    def rebuild(self, *, dry_run: bool = False, scope: str | None = None, market_id: str | None = None) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"written": False, "dry_run": dry_run, "candidates": 0, "results": []}
        results: list[dict[str, Any]] = []
        with self._factory.connect() as conn:
            if scope in {None, "no_trade"} and self._table_exists(conn, "no_trade_regret_score"):
                query = "SELECT DISTINCT no_trade_id FROM no_trade_regret_score"
                params: tuple[Any, ...] = ()
                if market_id:
                    query += " WHERE market_id=%s"
                    params = (market_id,)
                query += " ORDER BY no_trade_id LIMIT 50"
                candidates = [row["no_trade_id"] for row in conn.execute(query, params).fetchall()]
            else:
                candidates = []
        for candidate in candidates:
            results.append(self.review_no_trade(str(candidate), dry_run=dry_run))
        return {"written": not dry_run, "dry_run": dry_run, "candidates": len(candidates), "results": results}

    def recent_trade_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._recent("trade_reviews", limit)

    def signals(self) -> dict[str, Any]:
        return self._summary("signal_performance", self._signals.summary)

    def engines(self) -> dict[str, Any]:
        return self._summary("engine_learning", self._engines.summary)

    def sources(self) -> dict[str, Any]:
        return self._summary("source_learning", self._sources.summary)

    def whales(self) -> dict[str, Any]:
        return self._summary("whale_learning", self._whales.summary)

    def ai(self) -> dict[str, Any]:
        return self._summary("ai_learning", self._ai.summary)

    def no_trade(self) -> dict[str, Any]:
        return self._summary("no_trade_learning", self._no_trade.summary)

    def model_adjustments(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "items": []}
        with self._factory.connect() as conn:
            if not self._table_exists(conn, "model_adjustments"):
                return {"status": "EMPTY", "items": []}
            return {"status": "OK", "items": self._adjustments.pending(conn)}

    def snapshot(self) -> dict[str, Any]:
        return {
            "latest_reviews": self.recent_trade_reviews(limit=10),
            "engine_learning_summary": self.engines(),
            "source_learning_summary": self.sources(),
            "whale_learning_summary": self.whales(),
            "ai_learning_summary": self.ai(),
            "no_trade_learning_summary": self.no_trade(),
            "recommended_adjustments": self.model_adjustments(),
            "health": self.health(),
        }

    def _recent(self, table: str, limit: int) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            if not self._table_exists(conn, table):
                return []
            return recent(conn, table, limit)

    def _summary(self, table: str, summary_fn: Any) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "items": []}
        with self._factory.connect() as conn:
            if not self._table_exists(conn, table):
                return {"status": "EMPTY", "items": []}
            return {"status": "OK", "items": summary_fn(conn)}

    def _count_today(self, table: str) -> int:
        with self._factory.connect() as conn:
            if not self._table_exists(conn, table):
                return 0
            return count_today(conn, table)

    def _table_exists(self, conn: Any, table: str) -> bool:
        return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])

    def _publish(self, event_type: str, payload: dict[str, Any], aggregate_id: str) -> None:
        try:
            self._event_bus.publish(
                event_type,
                payload,
                source_service="learning.feedback_loop",
                aggregate_type="learning",
                aggregate_id=aggregate_id,
            )
        except Exception:
            return
