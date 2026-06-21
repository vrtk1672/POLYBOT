from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from targeted_revalidation_helpers import (
    insert_event_link,
    insert_fresh_orderbook,
    insert_market,
    insert_movement_after,
    insert_payout,
    setup_revalidation_tables,
)


def test_fresh_orderbook_liquidity_spread_payout_and_movement_states(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-state")
    insert_event_link("event-state", "market-state")
    insert_fresh_orderbook("market-state", liquidity=0.90, spread=0.01)
    insert_payout("market-state")
    insert_movement_after("market-state")

    TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM targeted_market_revalidations WHERE market_id='market-state'").fetchone()

    assert row["orderbook_refresh_state"] == "FRESH"
    assert row["liquidity_state"] == "GOOD"
    assert row["spread_state"] == "TIGHT"
    assert row["payout_odds_state"] == "AVAILABLE"
    assert row["movement_state"] == "MOVED_AFTER_EVENT"
    assert row["signal_state"] == "AVAILABLE"
    assert row["candidate_event_scope_state"] == "CANDIDATE_SCOPED"


def test_missing_orderbook_and_liquidity_do_not_fake_good_state(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-missing")
    insert_event_link("event-missing", "market-missing")

    TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM targeted_market_revalidations WHERE market_id='market-missing'").fetchone()

    assert row["revalidation_state"] == "PARTIAL"
    assert row["orderbook_refresh_state"] == "FAILED"
    assert row["liquidity_state"] == "UNKNOWN"
    assert row["eligible_for_candidate_generation_later"] is False
    assert "ORDERBOOK_NOT_FRESH" in row["candidate_generation_blockers_json"]


def test_token_conflict_and_token_side_unknown_block_candidate_readiness(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-conflict", token_state="TOKENS_MISMATCH")
    insert_market("market-unknown")
    insert_event_link("event-conflict", "market-conflict", token_side_state="TOKEN_SIDE_CONFLICT")
    insert_event_link("event-unknown", "market-unknown", token_side_state="TOKEN_SIDE_UNKNOWN")
    insert_fresh_orderbook("market-conflict")
    insert_fresh_orderbook("market-unknown")

    TargetedMarketRevalidationService().refresh(force=True, limit=10, skipped_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        rows = {
            row["market_id"]: row
            for row in conn.execute("SELECT * FROM targeted_market_revalidations ORDER BY market_id").fetchall()
        }

    assert rows["market-conflict"]["candidate_event_scope_state"] == "NOT_ACTIONABLE"
    assert "TOKEN_SIDE_CONFLICT" in rows["market-conflict"]["candidate_generation_blockers_json"]
    assert rows["market-unknown"]["candidate_event_scope_state"] == "MARKET_LEVEL_ONLY"
    assert "TOKEN_SIDE_NOT_CANDIDATE_ACTIONABLE" in rows["market-unknown"]["candidate_generation_blockers_json"]
