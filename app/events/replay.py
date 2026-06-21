from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.event_errors import EventReplayDenied
from app.events.envelope import EventEnvelope
from app.events.types import EventType
from app.repositories.event_replay_repository import EventReplayRepository
from app.repositories.event_store_repository import EventStoreRepository


LIVE_SIDE_EFFECT_EVENT_TYPES = {
    EventType.ORDER_INTENT_CREATED.value,
    EventType.ORDER_CREATED.value,
}


class EventReplayService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        store_repository: EventStoreRepository | None = None,
        replay_repository: EventReplayRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._store_repository = store_repository or EventStoreRepository()
        self._replay_repository = replay_repository or EventReplayRepository()

    def create_replay_job(self, *, requested_by: str, reason: str, filters: dict[str, Any]) -> str:
        if not requested_by.strip() or not reason.strip():
            raise ValueError("requested_by and reason are required")
        self._assert_safe_filter(filters)
        if not self._factory.enabled:
            raise RuntimeError("event replay requires database")
        with self._factory.connect() as conn, conn.transaction():
            return self._replay_repository.create_replay_job(
                conn,
                requested_by=requested_by,
                reason=reason,
                filters=filters,
            )

    def run_replay_job(self, replay_id: str) -> dict[str, int | str]:
        if not self._factory.enabled:
            raise RuntimeError("event replay requires database")
        with self._factory.connect() as conn, conn.transaction():
            job = self._replay_repository.get_replay_job(conn, replay_id)
            if job is None:
                raise ValueError(f"unknown replay job: {replay_id}")
            filters = dict(job["filter_json"] or {})
            self._assert_safe_filter(filters)
            self._replay_repository.mark_running(conn, replay_id)
            rows = self._store_repository.list_events_for_replay(conn, filters)
        replayed = 0
        failed = 0
        for row in rows:
            envelope = EventEnvelope.from_record(row)
            try:
                self._assert_safe_event(envelope)
                self._event_bus.dispatch_event(envelope, replay_metadata={"replay_id": replay_id})
                replayed += 1
            except Exception:
                failed += 1
        with self._factory.connect() as conn, conn.transaction():
            self._replay_repository.finish_job(
                conn,
                replay_id=replay_id,
                replayed_count=replayed,
                failed_count=failed,
            )
        return {"replay_id": replay_id, "replayed_count": replayed, "failed_count": failed}

    def replay_event(self, event_id: str) -> dict[str, int | str]:
        replay_id = self.create_replay_job(
            requested_by="system",
            reason="single event replay",
            filters={"event_id": event_id},
        )
        return self.run_replay_job(replay_id)

    def replay_by_filter(
        self,
        *,
        event_type: str | None = None,
        aggregate_id: str | None = None,
        correlation_id: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        requested_by: str = "system",
        reason: str = "filtered replay",
    ) -> dict[str, int | str]:
        filters = {
            key: value
            for key, value in {
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "correlation_id": correlation_id,
                "from_time": from_time,
                "to_time": to_time,
            }.items()
            if value is not None
        }
        replay_id = self.create_replay_job(requested_by=requested_by, reason=reason, filters=filters)
        return self.run_replay_job(replay_id)

    def _assert_safe_filter(self, filters: dict[str, Any]) -> None:
        if filters.get("event_type") in LIVE_SIDE_EFFECT_EVENT_TYPES:
            raise EventReplayDenied("replay of order side-effect events is blocked")
        if filters.get("event_id") and self._factory.enabled:
            with self._factory.connect() as conn:
                row = self._store_repository.get_event(conn, filters["event_id"])
            if row is not None:
                self._assert_safe_event(EventEnvelope.from_record(row))

    @staticmethod
    def _assert_safe_event(envelope: EventEnvelope) -> None:
        if envelope.event_type in LIVE_SIDE_EFFECT_EVENT_TYPES:
            raise EventReplayDenied("replay of order side-effect events is blocked")
