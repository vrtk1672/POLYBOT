from __future__ import annotations

from app.data_foundation.market_registry import MarketRegistry
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _raw(closed: bool = False) -> dict:
    return {
        "id": "m1",
        "question": "Will registry work?",
        "slug": "registry-work",
        "active": not closed,
        "closed": closed,
        "acceptingOrders": not closed,
        "clobTokenIds": ["yes", "no"],
        "description": "Rules text",
    }


def test_market_persisted_once_and_duplicate_updates(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    first = registry.normalize_market(_raw())
    _row, created = registry.upsert_market(first)
    assert created is True
    second = registry.normalize_market(_raw() | {"question": "Updated?"})
    _row, created = registry.upsert_market(second)
    assert created is False
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM markets_v2 WHERE market_id='m1'").fetchone()["count"]
        row = conn.execute("SELECT question, raw_market_json FROM markets_v2 WHERE market_id='m1'").fetchone()
    assert count == 1
    assert row["question"] == "Updated?"
    assert row["raw_market_json"]["slug"] == "registry-work"


def test_first_seen_market_emits_discovered(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market(_raw()))
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT event_type FROM event_log WHERE event_type='market.discovered'").fetchone()
    assert row is not None


def test_closed_market_updates_status(postgres_test_schema) -> None:
    run_migrations()
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market(_raw()))
    registry.upsert_market(registry.normalize_market(_raw(closed=True)))
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT closed, accepting_orders FROM markets_v2 WHERE market_id='m1'").fetchone()
        lifecycle = conn.execute("SELECT event_type FROM market_lifecycle_events WHERE event_type='CLOSED'").fetchone()
    assert row["closed"] is True
    assert row["accepting_orders"] is False
    assert lifecycle is not None
