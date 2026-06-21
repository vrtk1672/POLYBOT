from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.whale_neuron.contracts import stable_hash
from app.whale_neuron.redaction import redact_dict
from app.whale_neuron.source_registry import WhaleSourceRegistry


class WhaleScanner:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, whale_min_size_usd: float = 5000.0) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._sources = WhaleSourceRegistry(connection_factory=self._factory, event_bus=self._event_bus)
        self.whale_min_size_usd = whale_min_size_usd

    def scan_source(self, source_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        if source_id in {"manual", "mock"}:
            self._sources.update_fetch_status(source_id, success=True)
            return []
        self._sources.update_fetch_status(source_id, success=False, error="source scanner not configured")
        return []

    def scan_all_enabled(self, limit_per_source: int = 10) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        for source in self._sources.list_sources(enabled=True):
            try:
                events.extend(self.scan_source(str(source["source_id"]), limit=limit_per_source))
            except Exception as exc:
                self._sources.update_fetch_status(str(source["source_id"]), success=False, error=str(exc))
        return events

    def ingest_manual_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = dict(payload)
        event.setdefault("source_id", "manual")
        event.setdefault("event_time", datetime.now(UTC).isoformat())
        event["raw_event_hash"] = stable_hash(event)
        event["potential_whale"] = float(event.get("size_usd") or 0) >= self.whale_min_size_usd
        self._publish(EventType.WHALE_EVENT_COLLECTED, {"source_id": event["source_id"], "raw_event_hash": event["raw_event_hash"], "potential_whale": event["potential_whale"]})
        return redact_dict(event)

    def ingest_mock_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.ingest_manual_event({**event, "source_id": event.get("source_id", "mock")}) for event in events]

    def ingest_internal_paper_events(self) -> list[dict[str, Any]]:
        return []

    def _publish(self, event_type: EventType, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type.value, redact_dict(payload), "whale_neuron", aggregate_type="whale_event", aggregate_id=str(payload.get("raw_event_hash") or "unknown"))

