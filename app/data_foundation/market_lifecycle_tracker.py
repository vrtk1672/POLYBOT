from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.market_lifecycle_repository import MarketLifecycleRepository


class MarketLifecycleTracker:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = MarketLifecycleRepository()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)

    def detect_lifecycle_change(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        new_status = _status(current)
        previous_status = _status(previous) if previous else None
        if previous is None:
            return "DISCOVERED", previous_status, new_status
        if previous_status == new_status:
            return None, previous_status, new_status
        if new_status == "CLOSED":
            return "CLOSED", previous_status, new_status
        if new_status == "PAUSED":
            return "PAUSED", previous_status, new_status
        if previous_status in {"PAUSED", "STALE"} and new_status == "OPEN":
            return "REACTIVATED", previous_status, new_status
        return "UPDATED", previous_status, new_status

    def persist_lifecycle_event(
        self,
        market_id: str,
        event_type: str,
        *,
        previous_status: str | None = None,
        new_status: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn, conn.transaction():
            latest = self._repository.latest_event(conn, market_id)
            if latest and latest["event_type"] == event_type and latest["new_status"] == new_status:
                return latest
            row = self._repository.insert_event(
                conn,
                market_id=market_id,
                event_type=event_type,
                previous_status=previous_status,
                new_status=new_status,
                correlation_id=correlation_id,
                metadata=metadata,
            )
        self._publish(row)
        return row

    def mark_stale_if_needed(self, market: dict[str, Any], *, threshold_seconds: int = 300) -> dict[str, Any] | None:
        last_seen = market.get("last_seen_at")
        if last_seen is None:
            return None
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        if datetime.now(UTC) - last_seen <= timedelta(seconds=threshold_seconds):
            return None
        return self.persist_lifecycle_event(
            str(market["market_id"]),
            "STALE",
            previous_status=_status(market),
            new_status="STALE",
            metadata={"threshold_seconds": threshold_seconds},
        )

    def _publish(self, row: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(
                EventType.MARKET_LIFECYCLE_UPDATED.value,
                {"market_id": row["market_id"], "lifecycle_event_type": row["event_type"], "new_status": row["new_status"]},
                source_service="data_foundation",
                aggregate_type="market",
                aggregate_id=row["market_id"],
                correlation_id=row.get("correlation_id"),
                metadata={"non_trading_event": True},
            )
        except Exception:
            return


def _status(row: dict[str, Any] | None) -> str:
    if not row:
        return "UNKNOWN"
    if row.get("closed"):
        return "CLOSED"
    if row.get("accepting_orders") is False:
        return "PAUSED"
    if row.get("active") is False:
        return "ARCHIVED"
    return "OPEN"
