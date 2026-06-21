from __future__ import annotations

import inspect
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.consumer_registry import ConsumerRegistry, EventHandler
from app.events.envelope import EventEnvelope
from app.events.retry_policy import RetryPolicy
from app.events.types import validate_event_type
from app.logging import get_logger
from app.repositories.event_store_repository import EventStoreRepository

logger = get_logger(__name__)


class EventBus:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        consumer_registry: ConsumerRegistry | None = None,
        repository: EventStoreRepository | None = None,
        retry_policy: RetryPolicy | None = None,
        auto_dispatch: bool = True,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._registry = consumer_registry or ConsumerRegistry(connection_factory=self._factory)
        self._repository = repository or EventStoreRepository()
        self._retry_policy = retry_policy or RetryPolicy()
        self._auto_dispatch = auto_dispatch

    @property
    def consumer_registry(self) -> ConsumerRegistry:
        return self._registry

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        source_service: str,
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        cycle_id: str | None = None,
        mode: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        envelope_kwargs: dict[str, Any] = {
            "event_type": validate_event_type(event_type),
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "source_service": source_service,
            "causation_id": causation_id,
            "cycle_id": cycle_id,
            "mode": mode,
            "payload": payload,
            "metadata": metadata or {},
        }
        if correlation_id:
            envelope_kwargs["correlation_id"] = correlation_id
        envelope = EventEnvelope(
            **envelope_kwargs,
        )
        return self.publish_envelope(envelope)

    def publish_envelope(self, envelope: EventEnvelope) -> EventEnvelope:
        if self._factory.enabled:
            with self._factory.connect() as conn, conn.transaction():
                self._repository.append_event(conn, envelope)
        if self._auto_dispatch:
            self.dispatch_event(envelope)
        return envelope

    def subscribe(self, event_type: str, consumer_name: str, handler: EventHandler) -> None:
        self._registry.register_consumer(consumer_name, [event_type], handler)

    def subscribe_many(self, event_types: list[str], consumer_name: str, handler: EventHandler) -> None:
        self._registry.register_consumer(consumer_name, event_types, handler)

    def register_consumer(
        self,
        name: str,
        event_types: list[str],
        handler: EventHandler | None = None,
        group: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._registry.register_consumer(name, event_types, handler, group=group, metadata=metadata)

    def pause_consumer(self, consumer_name: str) -> None:
        self._registry.pause_consumer(consumer_name)

    def resume_consumer(self, consumer_name: str) -> None:
        self._registry.resume_consumer(consumer_name)

    def dispatch_pending(self, limit: int = 100) -> int:
        if not self._factory.enabled:
            return 0
        with self._factory.connect() as conn:
            rows = self._repository.list_recent_events(conn, limit=limit)
        dispatched = 0
        for row in reversed(rows):
            self.dispatch_event(EventEnvelope.from_record(row))
            dispatched += 1
        return dispatched

    def dispatch_event(self, envelope: EventEnvelope, *, replay_metadata: dict[str, Any] | None = None) -> None:
        consumers = self._registry.get_consumers_for_event_type(envelope.event_type)
        for consumer in consumers:
            consumer_name = consumer["consumer_name"]
            if consumer.get("status") != "ACTIVE":
                continue
            handler = consumer.get("handler") or self._registry.get_handler(consumer_name)
            if handler is None:
                continue
            self._dispatch_to_consumer(envelope, consumer_name, handler, replay_metadata=replay_metadata)

    def _dispatch_to_consumer(
        self,
        envelope: EventEnvelope,
        consumer_name: str,
        handler: EventHandler,
        *,
        replay_metadata: dict[str, Any] | None = None,
    ) -> None:
        attempt_number = self._next_attempt_number(envelope.event_id, consumer_name)
        try:
            result = handler(envelope)
            if inspect.isawaitable(result):
                raise RuntimeError("async event handlers are not supported by the in-process dispatcher yet")
            self._record_success(envelope, consumer_name, attempt_number, replay_metadata)
            self._registry.mark_consumer_success(consumer_name, envelope.event_id)
        except Exception as exc:
            logger.warning(
                "event_consumer_failed event_id=%s event_type=%s consumer=%s error=%s",
                envelope.event_id,
                envelope.event_type,
                consumer_name,
                exc,
            )
            self._record_failure(envelope, consumer_name, attempt_number, exc, replay_metadata)
            self._registry.mark_consumer_error(consumer_name, envelope.event_id)

    def _next_attempt_number(self, event_id: str, consumer_name: str) -> int:
        if not self._factory.enabled:
            return 1
        with self._factory.connect() as conn:
            return self._repository.delivery_attempt_count(conn, event_id, consumer_name) + 1

    def _record_success(
        self,
        envelope: EventEnvelope,
        consumer_name: str,
        attempt_number: int,
        replay_metadata: dict[str, Any] | None,
    ) -> None:
        if not self._factory.enabled:
            return
        with self._factory.connect() as conn, conn.transaction():
            self._repository.record_delivery_attempt(
                conn,
                event_id=envelope.event_id,
                consumer_name=consumer_name,
                attempt_number=attempt_number,
                status="SUCCESS",
                metadata=replay_metadata,
            )

    def _record_failure(
        self,
        envelope: EventEnvelope,
        consumer_name: str,
        attempt_number: int,
        exc: Exception,
        replay_metadata: dict[str, Any] | None,
    ) -> None:
        if not self._factory.enabled:
            return
        error_message = str(exc)
        with self._factory.connect() as conn, conn.transaction():
            if self._retry_policy.should_retry(attempt_number):
                self._repository.record_delivery_attempt(
                    conn,
                    event_id=envelope.event_id,
                    consumer_name=consumer_name,
                    attempt_number=attempt_number,
                    status="RETRY_SCHEDULED",
                    error_message=error_message,
                    next_retry_at=self._retry_policy.next_retry_at(attempt_number),
                    metadata=replay_metadata,
                )
                return
            self._repository.record_delivery_attempt(
                conn,
                event_id=envelope.event_id,
                consumer_name=consumer_name,
                attempt_number=attempt_number,
                status="DLQ",
                error_message=error_message,
                metadata=replay_metadata,
            )
            self._repository.move_to_dlq(
                conn,
                envelope=envelope,
                consumer_name=consumer_name,
                reason="max_attempts_exceeded",
                error_message=error_message,
                attempts=attempt_number,
                metadata=replay_metadata,
            )
