from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.whale_neuron.contracts import WhaleEvent
from app.whale_neuron.redaction import redact_dict


class WhaleRegistry:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleRegistryRepository()

    def upsert_whale(self, event: WhaleEvent) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"whale_id": event.whale_id, "wallet_address": event.wallet_address}
        with self._factory.connect() as conn, conn.transaction():
            row, created = self._repo.upsert_v27(
                conn,
                whale_id=event.whale_id or event.wallet_address or "unknown",
                wallet_address=event.wallet_address,
                display_label=event.trader_label,
                market_id=event.market_id,
                event_time=event.event_time,
                notional=event.notional or event.size_usd,
            )
        if created:
            self._event_bus.publish(EventType.WHALE_REGISTERED.value, redact_dict({"whale_id": event.whale_id, "wallet_address": event.wallet_address}), "whale_neuron", aggregate_type="whale", aggregate_id=event.whale_id or "unknown")
        return row

    def get_whale(self, whale_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repo.get_by_whale_id(conn, whale_id)

    def list_whales(self, *, status: str | None = None, min_notional: float | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repo.list_v27(conn, status=status, min_notional=min_notional, limit=limit)

    def update_whale_seen(self, event: WhaleEvent) -> dict[str, Any]:
        return self.upsert_whale(event)

    def update_total_events_and_notional(self, event: WhaleEvent) -> dict[str, Any]:
        return self.upsert_whale(event)

