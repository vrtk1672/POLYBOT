from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.envelope import EventEnvelope
from app.repositories.event_store_repository import EventStoreRepository


class EventStore:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: EventStoreRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or EventStoreRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def append_event(self, envelope: EventEnvelope) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.append_event(conn, envelope)

    def get_event(self, event_id: str) -> EventEnvelope | None:
        if not self._factory.enabled:
            return None
        with self._factory.connect() as conn:
            row = self._repository.get_event(conn, event_id)
        return EventEnvelope.from_record(row) if row else None

    def list_recent_events(self, **filters: Any) -> list[EventEnvelope]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_recent_events(conn, **filters)
        return [EventEnvelope.from_record(row) for row in rows]

    def list_events_for_replay(self, filters: dict[str, Any]) -> list[EventEnvelope]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = self._repository.list_events_for_replay(conn, filters)
        return [EventEnvelope.from_record(row) for row in rows]

    def metrics(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {
                "events_per_minute": 0.0,
                "failed_events": 0,
                "dlq_count": 0,
                "open_dlq_count": 0,
                "consumer_count": 0,
                "paused_consumers": 0,
                "last_event_time": None,
                "event_store_status": "DISABLED",
            }
        with self._factory.connect() as conn:
            metrics = self._repository.get_event_lag(conn)
            metrics["replay_jobs_running"] = self._repository.replay_jobs_running(conn)
        metrics["event_store_status"] = "HEALTHY"
        return metrics
