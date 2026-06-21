from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_source_repository import WhaleSourceRepository
from app.whale_neuron.contracts import WhaleSource, WhaleSourceType
from app.whale_neuron.redaction import redact_dict


class WhaleSourceRegistry:
    DEFAULT_SOURCE_TYPES = ["manual", "mock", "internal_paper", "polymarket_public", "clob_public", "csv_import"]

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleSourceRepository()

    def register_source(self, source: WhaleSource) -> dict[str, Any]:
        if not self._factory.enabled:
            return source.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row, created = self._repo.upsert_source(conn, source)
        if created:
            self._publish(EventType.WHALE_SOURCE_REGISTERED, {"source_id": source.source_id, "source_type": source.source_type.value})
        return dict(row)

    def enable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, True)

    def disable_source(self, source_id: str) -> None:
        self._set_enabled(source_id, False)

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            return self._repo.get_source(conn, source_id)

    def list_sources(self, *, enabled: bool | None = None, source_type: str | None = None) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            return self._repo.list_sources(conn, enabled=enabled, source_type=source_type.upper() if source_type else None)

    def update_fetch_status(self, source_id: str, *, success: bool, error: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repo.update_fetch_status(conn, source_id, success=success, error_message=error)

    def seed_default_sources(self) -> list[dict[str, Any]]:
        defaults = [
            WhaleSource(source_id="manual", name="Manual Whale Input", source_type=WhaleSourceType.MANUAL, platform="manual"),
            WhaleSource(source_id="mock", name="Mock Whale Feed", source_type=WhaleSourceType.MOCK, platform="mock", enabled=False),
            WhaleSource(source_id="internal_paper", name="Internal Paper Flow", source_type=WhaleSourceType.INTERNAL_PAPER, platform="polybot", enabled=False),
        ]
        return [self.register_source(source) for source in defaults]

    def _set_enabled(self, source_id: str, enabled: bool) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repo.set_enabled(conn, source_id, enabled)
        self._publish(EventType.WHALE_SOURCE_REGISTERED, {"source_id": source_id, "enabled": enabled})

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type.value, redact_dict(payload), "whale_neuron", aggregate_type="whale_source", aggregate_id=str(payload.get("source_id") or "unknown"))

