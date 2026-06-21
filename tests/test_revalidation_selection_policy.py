from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from targeted_revalidation_helpers import insert_event_link, insert_fresh_orderbook, insert_market, setup_revalidation_tables


def test_direct_and_high_confidence_likely_links_are_revalidated(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-direct")
    insert_market("market-likely")
    insert_event_link("event-direct", "market-direct", link_type="DIRECT_LINK", confidence=0.82)
    insert_event_link("event-likely", "market-likely", link_type="LIKELY_LINK", confidence=0.74)
    insert_fresh_orderbook("market-direct")
    insert_fresh_orderbook("market-likely")

    result = TargetedMarketRevalidationService().refresh(force=True, limit=10, skipped_sample_limit=0)

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        states = {
            row["market_id"]: row["revalidation_state"]
            for row in conn.execute("SELECT market_id, revalidation_state FROM targeted_market_revalidations").fetchall()
        }
    assert states["market-direct"] == "REVALIDATED"
    assert states["market-likely"] == "REVALIDATED"


def test_weak_context_no_link_watch_and_low_confidence_likely_are_skipped(postgres_test_schema) -> None:
    setup_revalidation_tables()
    for suffix, link_type, confidence, hint in (
        ("weak", "WEAK_LINK", 0.50, "WATCH_ONLY"),
        ("context", "CONTEXT_ONLY", 0.40, "CONTEXT_ONLY"),
        ("no", "NO_LINK", 0.0, "NOT_RELEVANT"),
        ("watch", "DIRECT_LINK", 0.90, "WATCH_ONLY"),
        ("low-likely", "LIKELY_LINK", 0.55, "REVALIDATION_ELIGIBLE"),
    ):
        market_id = f"market-{suffix}"
        insert_market(market_id)
        insert_event_link(f"event-{suffix}", market_id, link_type=link_type, confidence=confidence, hint=hint)

    result = TargetedMarketRevalidationService().refresh(force=True, limit=10, skipped_sample_limit=10)

    assert result["links_revalidated"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute("SELECT revalidation_state, skip_reason FROM targeted_market_revalidations").fetchall()
    assert {row["revalidation_state"] for row in rows} == {"SKIPPED"}
    assert any("WEAK_LINK" in row["skip_reason"] for row in rows)
    assert any("CONTEXT_ONLY" in row["skip_reason"] for row in rows)
    assert any("WATCH_ONLY" in row["skip_reason"] for row in rows)
