from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.source_event_memory import SourceEventMemoryService
from source_event_memory_helpers import insert_market, insert_news_event, setup_source_event_tables


def test_source_event_upsert_creates_canonical_memory_row(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-direct", title="Will Kraken IPO in 2026?", entities=["Kraken"], tags=["crypto"], keywords=["kraken", "ipo"])
    insert_news_event(
        "event-direct",
        title="Kraken IPO plans advance",
        summary="Kraken listing plans may affect prediction markets.",
        market_id="market-direct",
        direction="YES",
        confidence=0.91,
    )

    result = SourceEventMemoryService().refresh_events(force=True)

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM source_event_memory WHERE source_record_id='event-direct'").fetchone()
        link = conn.execute("SELECT * FROM event_to_market_recall WHERE market_id='market-direct'").fetchone()

    assert row["source_type"] in {"NEWS", "RSS"}
    assert row["headline"] == "Kraken IPO plans advance"
    assert row["direction"] == "YES"
    assert "kraken" in row["keywords_json"]
    assert link["link_type"] == "DIRECT_LINK"
    assert link["eligible_for_targeted_revalidation"] is True


def test_unknown_extraction_and_direction_are_preserved_safely(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-context", title="Will a new policy pass?", tags=["politics"], keywords=["policy"])
    insert_news_event("event-unknown", title="Brief update", summary="", direction="UNKNOWN", confidence=0.0)

    SourceEventMemoryService().refresh_events(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM source_event_memory WHERE source_record_id='event-unknown'").fetchone()
        link = conn.execute("SELECT * FROM event_to_market_recall WHERE source_event_id=%s", (row["source_event_id"],)).fetchone()

    assert row["direction"] == "UNKNOWN"
    assert row["direction_confidence"] == 0
    assert row["already_priced_in_state"] in {"UNKNOWN", "NOT_EVALUATED"}
    assert link["link_type"] == "NO_LINK"


def test_refresh_does_not_create_paper_or_live_artifacts(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-safe", title="Will safety remain true?", keywords=["safety"])
    insert_news_event("event-safe", title="Safety update remains informational", market_id="market-safe", confidence=0.85)

    with DatabaseConnectionFactory().connect() as conn:
        before = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions")
        }

    result = SourceEventMemoryService().refresh_events(force=True)

    with DatabaseConnectionFactory().connect() as conn:
        after = {
            table: conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "positions")
        }
        latest = conn.execute("SELECT metadata_json FROM source_event_memory_refresh_runs ORDER BY id DESC LIMIT 1").fetchone()

    assert result["status"] == "OK"
    assert after == before
    assert latest["metadata_json"]["execution_candidates_created"] is False
    assert latest["metadata_json"]["targeted_revalidation_triggered"] is False
