from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.envelope import EventEnvelope
from app.events.types import validate_event_type
from app.repositories.event_consumer_repository import EventConsumerRepository

EventHandler = Callable[[EventEnvelope], Any]


class ConsumerRegistry:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: EventConsumerRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or EventConsumerRepository()
        self._handlers: dict[str, EventHandler] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._paused_consumers: set[str] = set()

    def register_consumer(
        self,
        name: str,
        event_types: list[str],
        handler_ref: EventHandler | None = None,
        group: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized = [validate_event_type(event_type) for event_type in event_types]
        if handler_ref is not None:
            self._handlers[name] = handler_ref
        self._subscriptions[name] = set(normalized)
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.register_consumer(
                    conn,
                    consumer_name=name,
                    event_types=normalized,
                    group=group,
                    metadata=metadata,
                )

    def get_consumers_for_event_type(self, event_type: str) -> list[dict[str, Any]]:
        event_type = validate_event_type(event_type)
        consumers: dict[str, dict[str, Any]] = {}
        for name, subscriptions in self._subscriptions.items():
            if event_type in subscriptions:
                consumers[name] = {
                    "consumer_name": name,
                    "status": "PAUSED" if name in self._paused_consumers else "ACTIVE",
                    "handler": self._handlers.get(name),
                }
        if self._factory.enabled:
            with self._factory.connect() as conn:
                for row in self._repository.get_consumers_for_event_type(conn, event_type):
                    consumers[row["consumer_name"]] = dict(row) | {"handler": self._handlers.get(row["consumer_name"])}
        return list(consumers.values())

    def list_consumers(self) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return [
                {
                    "consumer_name": name,
                    "subscribed_event_types": sorted(event_types),
                    "status": "ACTIVE",
                }
                for name, event_types in sorted(self._subscriptions.items())
            ]
        with self._factory.connect() as conn:
            return [dict(row) for row in self._repository.list_consumers(conn)]

    def get_handler(self, consumer_name: str) -> EventHandler | None:
        return self._handlers.get(consumer_name)

    def mark_consumer_seen(self, consumer_name: str, event_id: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_seen(conn, consumer_name, event_id)

    def mark_consumer_success(self, consumer_name: str, event_id: str) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_success(conn, consumer_name, event_id)

    def mark_consumer_error(self, consumer_name: str, event_id: str | None = None) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.mark_error(conn, consumer_name, event_id)

    def pause_consumer(self, consumer_name: str) -> None:
        self._paused_consumers.add(consumer_name)
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.pause_consumer(conn, consumer_name)

    def resume_consumer(self, consumer_name: str) -> None:
        self._paused_consumers.discard(consumer_name)
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.resume_consumer(conn, consumer_name)
