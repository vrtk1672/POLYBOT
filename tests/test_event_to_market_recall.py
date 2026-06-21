from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.source_event_memory import SourceEventMemoryService
from source_event_memory_helpers import insert_market, insert_news_event, setup_source_event_tables


def _link_for(event_id: str):
    with DatabaseConnectionFactory().connect() as conn:
        event = conn.execute("SELECT source_event_id FROM source_event_memory WHERE source_record_id=%s", (event_id,)).fetchone()
        return conn.execute(
            """
            SELECT *
            FROM event_to_market_recall
            WHERE source_event_id=%s
            ORDER BY link_confidence DESC
            LIMIT 1
            """,
            (event["source_event_id"],),
        ).fetchone()


def test_direct_likely_weak_and_unlinked_recall_states(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-direct", title="Will Direct Link pass?", keywords=["direct", "link"])
    insert_market("market-likely", title="Will unrelated alpha resolve?", keywords=["alpha"])
    insert_market("market-weak", title="Will unrelated beta resolve?", keywords=["beta"])

    insert_news_event("event-direct", title="Direct Link update", market_id="market-direct", direction="YES", confidence=0.9)
    insert_news_event("event-likely", title="Likely Link update", market_id="market-likely", direction="NO", confidence=0.72)
    insert_news_event("event-weak", title="Weak Link update", market_id="market-weak", direction="MIXED", confidence=0.4)
    insert_news_event("event-none", title="Unrelated tennis result", summary="Nothing about these markets.")

    SourceEventMemoryService().refresh_events(force=True)

    direct = _link_for("event-direct")
    likely = _link_for("event-likely")
    weak = _link_for("event-weak")
    none = _link_for("event-none")

    assert direct["link_type"] == "DIRECT_LINK"
    assert direct["direction_for_market"] == "YES"
    assert likely["link_type"] == "LIKELY_LINK"
    assert likely["direction_for_market"] == "NO"
    assert weak["link_type"] == "WEAK_LINK"
    assert weak["direction_for_market"] == "MIXED"
    assert none["link_type"] == "NO_LINK"
    assert none["eligible_for_targeted_revalidation"] is False


def test_low_confidence_links_are_not_targeted_revalidation_ready(postgres_test_schema) -> None:
    setup_source_event_tables()
    insert_market("market-low", title="Will low confidence stay contextual?", keywords=["low", "confidence"])
    insert_news_event("event-low", title="Low Confidence update", market_id="market-low", confidence=0.3)

    SourceEventMemoryService().refresh_events(force=True)

    link = _link_for("event-low")
    assert link["link_type"] in {"WEAK_LINK", "CONTEXT_ONLY", "NO_LINK"}
    assert link["eligible_for_targeted_revalidation"] is False
