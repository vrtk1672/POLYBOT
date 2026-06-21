from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.event_bus import EventBus
from app.events.retry_policy import RetryPolicy
from app.events.types import EventType
from app.repositories.event_store_repository import EventStoreRepository


def _bus(postgres_test_schema, *, max_attempts: int = 3) -> EventBus:
    run_migrations()
    return EventBus(
        connection_factory=DatabaseConnectionFactory(),
        retry_policy=RetryPolicy(max_attempts=max_attempts, backoff_seconds=[1, 1, 1]),
    )


def test_publish_stores_event_and_returns_envelope(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    assert envelope.event_id
    with DatabaseConnectionFactory().connect() as conn:
        row = EventStoreRepository().get_event(conn, envelope.event_id)
    assert row is not None


def test_publish_creates_correlation_id_if_missing(postgres_test_schema) -> None:
    envelope = _bus(postgres_test_schema).publish(
        EventType.RUNTIME_CYCLE_STARTED.value,
        {"ok": True},
        source_service="test",
    )
    assert envelope.correlation_id.startswith("corr_")


def test_publish_preserves_provided_correlation_id(postgres_test_schema) -> None:
    envelope = _bus(postgres_test_schema).publish(
        EventType.RUNTIME_CYCLE_STARTED.value,
        {"ok": True},
        source_service="test",
        correlation_id="corr_given",
    )
    assert envelope.correlation_id == "corr_given"


def test_in_process_consumer_receives_event(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    seen: list[str] = []
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "consumer_a", lambda event: seen.append(event.event_id))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    assert seen == [envelope.event_id]


def test_consumer_failure_does_not_crash_publish(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)

    def failing_handler(_event):
        raise RuntimeError("boom")

    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "bad_consumer", failing_handler)
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    assert envelope.event_id
    with DatabaseConnectionFactory().connect() as conn:
        attempts = conn.execute(
            "SELECT * FROM event_delivery_attempts WHERE event_id = %s",
            (envelope.event_id,),
        ).fetchall()
    assert attempts[0]["status"] == "RETRY_SCHEDULED"
