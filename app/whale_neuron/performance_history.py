from __future__ import annotations

from uuid import uuid4

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_event_repository import WhaleEventRepository
from app.repositories.whale_performance_repository import WhalePerformanceRepository
from app.whale_neuron.redaction import redact_dict


class WhalePerformanceHistory:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._events = WhaleEventRepository()
        self._repo = WhalePerformanceRepository()

    def evaluate_event_performance(self, whale_event_id: str) -> dict[str, object]:
        if not self._factory.enabled:
            return {"follow_result": "INSUFFICIENT_DATA", "reason": "database unavailable"}
        with self._factory.connect() as conn:
            event = self._events.get_event(conn, whale_event_id)
            if not event:
                return {"follow_result": "INSUFFICIENT_DATA", "reason": "event missing"}
            snapshot = None
            if event.get("market_id") and event.get("price") is not None:
                snapshot = conn.execute(
                    "SELECT yes_price, price FROM market_snapshots_v2 WHERE market_id = %s AND captured_at > %s ORDER BY captured_at ASC LIMIT 1",
                    (event["market_id"], event["event_time"]),
                ).fetchone()
        result = self._evaluate_from_snapshot(event, snapshot)
        self.record_performance(result)
        return result

    def evaluate_whale_market_outcome(self, whale_id: str, market_id: str) -> dict[str, object]:
        return {"whale_id": whale_id, "market_id": market_id, "follow_result": "INSUFFICIENT_DATA", "reason": "market outcome unavailable"}

    def record_performance(self, record: dict[str, object]) -> dict[str, object]:
        record.setdefault("whale_performance_id", f"whale_perf_{uuid4().hex}")
        if not self._factory.enabled:
            return record
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.insert_record(conn, record)
        self._event_bus.publish(EventType.WHALE_PERFORMANCE_UPDATED.value, redact_dict(record), "whale_neuron", aggregate_type="whale", aggregate_id=str(record.get("whale_id") or "unknown"))
        return row

    def update_profile_from_performance(self, whale_id: str) -> dict[str, object]:
        from app.whale_neuron.profile_builder import WhaleProfileBuilder

        return WhaleProfileBuilder(connection_factory=self._factory, event_bus=self._event_bus).rebuild_whale_profile(whale_id).model_dump(mode="json")

    def _evaluate_from_snapshot(self, event: dict[str, object], snapshot: dict[str, object] | None) -> dict[str, object]:
        if not snapshot or event.get("price") is None:
            return {"whale_id": event.get("whale_id"), "market_id": event.get("market_id"), "whale_event_id": event.get("whale_event_id"), "follow_result": "INSUFFICIENT_DATA", "timing_quality": 0.0}
        later_price = snapshot.get("yes_price") if snapshot.get("yes_price") is not None else snapshot.get("price")
        pnl_proxy = float(later_price) - float(event["price"])
        good = pnl_proxy >= 0 if event.get("side") == "YES" else pnl_proxy <= 0
        return {
            "whale_id": event.get("whale_id"),
            "market_id": event.get("market_id"),
            "whale_event_id": event.get("whale_event_id"),
            "observed_outcome": "PRICE_PROXY",
            "pnl_proxy": pnl_proxy,
            "timing_quality": 0.75 if good else 0.2,
            "entry_quality": 0.75 if good else 0.2,
            "follow_result": "GOOD_FOLLOW" if good else "BAD_FOLLOW",
            "was_early": good,
            "was_late": not good,
            "was_noisy": False,
        }

