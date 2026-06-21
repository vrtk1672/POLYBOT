from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.event_bus import EventBus
from app.events.event_errors import EventReplayDenied
from app.events.replay import EventReplayService
from app.events.types import EventType


def _services(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    bus = EventBus(connection_factory=factory)
    return factory, bus, EventReplayService(connection_factory=factory, event_bus=bus)


def test_create_replay_job(postgres_test_schema) -> None:
    _factory, _bus, replay = _services(postgres_test_schema)
    replay_id = replay.create_replay_job(
        requested_by="operator",
        reason="consumer fix",
        filters={"event_type": EventType.RUNTIME_CYCLE_STARTED.value},
    )
    assert replay_id.startswith("replay_")


def test_replay_single_event(postgres_test_schema) -> None:
    _factory, bus, replay = _services(postgres_test_schema)
    seen: list[str] = []
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "replay_consumer", lambda event: seen.append(event.event_id))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    seen.clear()
    replay_id = replay.create_replay_job(requested_by="operator", reason="safe replay", filters={"event_id": envelope.event_id})
    result = replay.run_replay_job(replay_id)
    assert result["replayed_count"] == 1
    assert seen == [envelope.event_id]


def test_replay_by_event_type(postgres_test_schema) -> None:
    _factory, bus, replay = _services(postgres_test_schema)
    seen: list[str] = []
    bus.subscribe(EventType.RUNTIME_CYCLE_FINISHED.value, "finish_replay", lambda event: seen.append(event.event_id))
    first = bus.publish(EventType.RUNTIME_CYCLE_FINISHED.value, {"status": "ok"}, source_service="test")
    bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"status": "start"}, source_service="test")
    seen.clear()
    result = replay.replay_by_filter(
        event_type=EventType.RUNTIME_CYCLE_FINISHED.value,
        requested_by="operator",
        reason="filtered replay",
    )
    assert result["replayed_count"] == 1
    assert seen == [first.event_id]


def test_replay_preserves_original_event_id_in_attempt_metadata(postgres_test_schema) -> None:
    factory, bus, replay = _services(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "metadata_replay", lambda event: None)
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    replay_id = replay.create_replay_job(requested_by="operator", reason="metadata", filters={"event_id": envelope.event_id})
    replay.run_replay_job(replay_id)
    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM event_log WHERE event_id = %s",
            (envelope.event_id,),
        ).fetchall()
        attempts = conn.execute(
            """
            SELECT metadata_json
            FROM event_delivery_attempts
            WHERE event_id = %s AND metadata_json ? 'replay_id'
            """,
            (envelope.event_id,),
        ).fetchall()
    assert len(rows) == 1
    assert attempts[-1]["metadata_json"]["replay_id"] == replay_id


def test_replay_failure_recorded(postgres_test_schema) -> None:
    _factory, bus, replay = _services(postgres_test_schema)
    bus.subscribe(EventType.RUNTIME_CYCLE_STARTED.value, "failing_replay", lambda event: (_ for _ in ()).throw(RuntimeError("fail")))
    envelope = bus.publish(EventType.RUNTIME_CYCLE_STARTED.value, {"ok": True}, source_service="test")
    replay_id = replay.create_replay_job(requested_by="operator", reason="failure", filters={"event_id": envelope.event_id})
    result = replay.run_replay_job(replay_id)
    assert result["replayed_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        job = conn.execute("SELECT status FROM event_replay_jobs WHERE replay_id = %s", (replay_id,)).fetchone()
    assert job["status"] == "COMPLETED"


def test_replay_blocks_order_side_effect_events(postgres_test_schema) -> None:
    _factory, bus, replay = _services(postgres_test_schema)
    envelope = bus.publish(EventType.ORDER_CREATED.value, {"order_id": "o1"}, source_service="test")
    with pytest.raises(EventReplayDenied):
        replay.create_replay_job(requested_by="operator", reason="unsafe", filters={"event_id": envelope.event_id})
