from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_candidate_generation import ProactiveCandidateGenerationService
from proactive_candidate_generation_helpers import setup_proactive_seed_source


def test_token_side_unknown_does_not_create_actionable_side_seed(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-token-unknown", direction="YES", token_side_state="TOKEN_SIDE_UNKNOWN")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT side, token_id, seed_state, soft_warnings_json FROM proactive_candidate_seeds WHERE market_id='market-stage4-token-unknown'").fetchone()
    assert row["seed_state"] == "WATCH_ONLY"
    assert row["side"] == "SIDE_UNKNOWN"
    assert row["token_id"] is None
    assert "TOKEN_SIDE_UNKNOWN_WATCH_ONLY" in row["soft_warnings_json"]


def test_token_conflict_blocks_seed(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-token-conflict", direction="YES", token_side_state="TOKEN_SIDE_CONFLICT")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT seed_state, blockers_json FROM proactive_candidate_seeds WHERE market_id='market-stage4-token-conflict'").fetchone()
    assert row["seed_state"] == "BLOCKED"
    assert "TOKEN_SIDE_CONFLICT" in row["blockers_json"]


def test_stale_orderbook_blocks_seed_generation(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-stale-ob", stale_orderbook=True)

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT seed_state, blockers_json FROM proactive_candidate_seeds WHERE market_id='market-stage4-stale-ob'").fetchone()
    assert row["seed_state"] == "BLOCKED"
    assert "ORDERBOOK_NOT_FRESH" in row["blockers_json"]


def test_unresolved_or_closed_market_blocks_seed_generation(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-unresolved", identity_state="UNRESOLVED")
    setup_proactive_seed_source("market-stage4-closed", market_status="CLOSED")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        rows = {
            row["market_id"]: row["blockers_json"]
            for row in conn.execute("SELECT market_id, blockers_json FROM proactive_candidate_seeds WHERE market_id LIKE 'market-stage4-%'").fetchall()
        }
    assert "MARKET_IDENTITY_NOT_VERIFIED" in rows["market-stage4-unresolved"]
    assert "MARKET_NOT_ACTIVE" in rows["market-stage4-closed"]


def test_already_priced_in_yes_downgrades_to_watch_only_warning(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-priced", already_priced_in="YES")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT seed_state, side, soft_warnings_json FROM proactive_candidate_seeds WHERE market_id='market-stage4-priced'").fetchone()
    assert row["seed_state"] == "WATCH_ONLY"
    assert row["side"] == "SIDE_UNKNOWN"
    assert "EVENT_ALREADY_PRICED_IN" in row["soft_warnings_json"]
