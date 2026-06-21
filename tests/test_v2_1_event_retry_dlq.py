from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.dlq import DeadLetterQueue
from app.events.event_bus import EventBus
from app.events.retry_policy import RetryPolicy
from app.events.types import EventType


def _bus(postgres_test_schema) -> EventBus:
    run_migrations()
    return EventBus(
        connection_factory=DatabaseConnectionFactory(),
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=[1, 1, 1]),
    )


def test_failed_handler_records_delivery_attempt_and_retry(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "fails_once", lambda event: (_ for _ in ()).throw(RuntimeError("fail")))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(
            "SELECT status, next_retry_at FROM event_delivery_attempts WHERE event_id = %s",
            (envelope.event_id,),
        ).fetchone()
    assert row["status"] == "RETRY_SCHEDULED"
    assert row["next_retry_at"] is not None


def test_after_max_attempts_moves_to_dlq(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)

    def fail(_event):
        raise RuntimeError("still failing")

    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "dlq_consumer", fail)
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"secret": "hide me"}, source_service="test")
    bus.dispatch_event(envelope)
    bus.dispatch_event(envelope)
    with DatabaseConnectionFactory().connect() as conn:
        dlq = conn.execute("SELECT * FROM event_dlq WHERE event_id = %s", (envelope.event_id,)).fetchone()
    assert dlq["reason"] == "max_attempts_exceeded"
    assert dlq["attempts"] == 3
    assert dlq["failed_payload_json"]["secret"] == "<redacted>"


def test_dlq_item_can_be_marked_resolved_or_ignored(postgres_test_schema) -> None:
    bus = _bus(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "dlq_marker", lambda event: (_ for _ in ()).throw(RuntimeError("fail")))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    bus.dispatch_event(envelope)
    bus.dispatch_event(envelope)
    dlq_service = DeadLetterQueue(connection_factory=DatabaseConnectionFactory())
    item = dlq_service.list_dlq()[0]
    dlq_service.mark_dlq_resolved(item["id"])
    with DatabaseConnectionFactory().connect() as conn:
        resolved = conn.execute("SELECT status FROM event_dlq WHERE id = %s", (item["id"],)).fetchone()
    assert resolved["status"] == "RESOLVED"
    dlq_service.mark_dlq_ignored(item["id"])
    with DatabaseConnectionFactory().connect() as conn:
        ignored = conn.execute("SELECT status FROM event_dlq WHERE id = %s", (item["id"],)).fetchone()
    assert ignored["status"] == "IGNORED"
