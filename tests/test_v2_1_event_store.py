from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.events.envelope import EventEnvelope
from app.events.types import EventType
from app.repositories.event_store_repository import EventStoreRepository


def _setup(postgres_test_schema):
    run_migrations()
    return DatabaseConnectionFactory(), EventStoreRepository()


def _envelope(correlation_id: str = "corr_test") -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.MARKET_SNAPSHOT_CREATED.value,
        source_service="test",
        correlation_id=correlation_id,
        aggregate_type="market",
        aggregate_id="m1",
        payload={"market_id": "m1", "price": 0.42},
        metadata={"phase": "v2.1"},
    )


def test_append_event_writes_to_event_log(postgres_test_schema) -> None:
    factory, repo = _setup(postgres_test_schema)
    envelope = _envelope()
    with factory.connect() as conn, conn.transaction():
        repo.append_event(conn, envelope)
        row = repo.get_event(conn, envelope.event_id)
    assert row is not None
    assert row["event_type"] == EventType.MARKET_SNAPSHOT_CREATED.value


def test_event_id_is_unique(postgres_test_schema) -> None:
    factory, repo = _setup(postgres_test_schema)
    envelope = _envelope()
    with factory.connect() as conn, conn.transaction():
        repo.append_event(conn, envelope)
    with pytest.raises(Exception):
        with factory.connect() as conn, conn.transaction():
            repo.append_event(conn, envelope)


def test_payload_metadata_and_correlation_persist(postgres_test_schema) -> None:
    factory, repo = _setup(postgres_test_schema)
    envelope = _envelope(correlation_id="corr_keep")
    with factory.connect() as conn, conn.transaction():
        repo.append_event(conn, envelope)
        row = repo.get_event(conn, envelope.event_id)
    assert row["payload_json"]["market_id"] == "m1"
    assert row["metadata_json"]["phase"] == "v2.1"
    assert row["correlation_id"] == "corr_keep"


def test_list_recent_and_filters_work(postgres_test_schema) -> None:
    factory, repo = _setup(postgres_test_schema)
    first = _envelope(correlation_id="corr_a")
    second = EventEnvelope(
        event_type=EventType.RUNTIME_CYCLE_STARTED.value,
        source_service="test",
        correlation_id="corr_b",
        payload={"cycle": "start"},
    )
    with factory.connect() as conn, conn.transaction():
        repo.append_event(conn, first)
        repo.append_event(conn, second)
        recent = repo.list_recent_events(conn, limit=10)
        by_type = repo.list_recent_events(conn, limit=10, event_type=EventType.RUNTIME_CYCLE_STARTED.value)
        by_corr = repo.list_recent_events(conn, limit=10, correlation_id="corr_a")
    assert len(recent) == 2
    assert [row["event_id"] for row in by_type] == [second.event_id]
    assert [row["event_id"] for row in by_corr] == [first.event_id]
