from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.targeted_market_revalidation import TargetedMarketRevalidationService
from targeted_revalidation_helpers import artifact_counts, insert_event_link, insert_fresh_orderbook, insert_market, setup_revalidation_tables


def test_candidate_generation_later_requires_strong_link_verified_identity_tokens_fresh_orderbook_and_active_market(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-ready")
    insert_event_link("event-ready", "market-ready", link_type="DIRECT_LINK", confidence=0.90, token_side_state="SIDE_DIRECTIONAL_YES")
    insert_fresh_orderbook("market-ready", liquidity=0.80, spread=0.01)

    TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM targeted_market_revalidations WHERE market_id='market-ready'").fetchone()

    assert row["revalidation_state"] == "REVALIDATED"
    assert row["eligible_for_candidate_generation_later"] is True
    assert row["candidate_generation_blockers_json"] == []


def test_already_priced_in_unknown_is_allowed_when_movement_data_is_insufficient(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-unknown-priced")
    insert_event_link("event-unknown-priced", "market-unknown-priced")
    insert_fresh_orderbook("market-unknown-priced")

    TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT already_priced_in_state, already_priced_in_reason FROM targeted_market_revalidations WHERE market_id='market-unknown-priced'").fetchone()

    assert row["already_priced_in_state"] == "UNKNOWN"
    assert row["already_priced_in_reason"]


def test_stage3_does_not_create_execution_candidates_or_paper_artifacts(postgres_test_schema) -> None:
    setup_revalidation_tables()
    insert_market("market-safe-stage3")
    insert_event_link("event-safe-stage3", "market-safe-stage3")
    insert_fresh_orderbook("market-safe-stage3")
    before = artifact_counts()

    result = TargetedMarketRevalidationService().refresh(force=True, limit=5, skipped_sample_limit=0)
    after = artifact_counts()

    assert result["status"] == "OK"
    assert after == before
    with DatabaseConnectionFactory().connect() as conn:
        candidates = [
            row["table_name"]
            for row in conn.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = ANY(current_schemas(false))
                  AND table_name LIKE '%candidate%'
                """
            ).fetchall()
        ]
    assert "targeted_market_revalidations" not in candidates
