from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.event_bus import EventBus
from app.events.types import EventType


def _bus(postgres_test_schema) -> EventBus:
    run_migrations()
    return EventBus(connection_factory=DatabaseConnectionFactory())


def test_register_and_list_consumer(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    bus.register_consumer("audit_consumer", [EventType.RUNTIME_CYCLE_STARTED.value], lambda event: None)
    consumers = bus.consumer_registry.list_consumers()
    assert any(row["consumer_name"] == "audit_consumer" for row in consumers)


def test_subscribe_to_event_type(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "seen_consumer", lambda event: None)
    consumers = bus.consumer_registry.get_consumers_for_event_type(EventType.RUNTIME_CYCLE_STARTED.value)
    assert any(row["consumer_name"] == "seen_consumer" for row in consumers)


def test_pause_consumer_blocks_dispatch_and_resume_allows(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    seen: list[str] = []
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "pausable", lambda event: seen.append(event.event_id))
    bus.pause_consumer("pausable")
    bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"n": 1}, source_service="test")
    assert seen == []
    bus.resume_consumer("pausable")
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"n": 2}, source_service="test")
    assert seen == [envelope.event_id]


def test_consumer_status_updates_on_success_and_error(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "status_consumer", lambda event: None)
    bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"n": 1}, source_service="test")
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT status, last_success_at FROM event_consumers WHERE consumer_name = 'status_consumer'"
        ).fetchone()
    assert row["status"] == "ACTIVE"
    assert row["last_success_at"] is not None

    def fail(_event):
        raise RuntimeError("nope")

    bus.subscribe(EventType.RUNTIME_CYCLE_FINISHED.value, "error_consumer", fail)
    bus.publish(EventType.RUNTIME_CYCLE_FINISHED.value, {"n": 2}, source_service="test")
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT status, error_count FROM event_consumers WHERE consumer_name = 'error_consumer'"
        ).fetchone()
    assert row["status"] == "ERROR"
    assert row["error_count"] == 1
