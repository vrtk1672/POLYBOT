from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.source_event_memory import SourceEventMemoryService
from source_event_memory_helpers import insert_market, insert_news_event, setup_source_event_tables


def test_duplicate_source_event_updates_existing_row_not_duplicate(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-dedupe", title="Will duplicate event dedupe?", keywords=["duplicate", "event"])
    insert_news_event(
        "event-dedupe",
        title="Duplicate event update",
        summary="Initial text",
        market_id="market-dedupe",
        confidence=0.9,
    )

    first = SourceEventMemoryService().refresh_events(force=True)
    second = SourceEventMemoryService().refresh_events(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM source_event_memory").fetchone()["count"]
        link_count = conn.execute("SELECT COUNT(*) AS count FROM event_to_market_recall").fetchone()["count"]

    assert first["events_new"] == 1
    assert second["events_updated"] == 1
    assert second["duplicate_events"] == 1
    assert count == 1
    assert link_count == 1
