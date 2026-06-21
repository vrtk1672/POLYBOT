from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.proactive_candidate_generation import ProactiveCandidateGenerationService
from proactive_candidate_generation_helpers import seed_artifact_counts, setup_proactive_seed_source


def test_clean_yes_revalidation_creates_yes_research_seed(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-yes", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")

    before = seed_artifact_counts()
    result = ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)
    after = seed_artifact_counts()

    assert result["status"] == "OK"
    assert after == before
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM proactive_candidate_seeds WHERE market_id='market-stage4-yes'").fetchone()
    assert row["seed_state"] == "GENERATED"
    assert row["side"] == "YES"
    assert row["token_id"] == "market-stage4-yes-yes"
    assert row["research_only"] is True
    assert row["execution_allowed"] is False
    assert row["paper_allowed"] is False
    assert row["shadow_allowed"] is False
    assert row["live_allowed"] is False


def test_clean_no_revalidation_creates_no_research_seed(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-no", direction="NO", token_side_state="SIDE_DIRECTIONAL_NO")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT side, token_id, seed_state FROM proactive_candidate_seeds WHERE market_id='market-stage4-no'").fetchone()
    assert row["seed_state"] == "GENERATED"
    assert row["side"] == "NO"
    assert row["token_id"] == "market-stage4-no-no"


def test_unknown_direction_creates_watch_only_side_unknown_seed(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-unknown", direction="UNKNOWN", token_side_state="TOKEN_SIDE_UNKNOWN")

    ProactiveCandidateGenerationService().refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT side, token_id, seed_state, execution_allowed FROM proactive_candidate_seeds WHERE market_id='market-stage4-unknown'").fetchone()
    assert row["seed_state"] == "WATCH_ONLY"
    assert row["side"] == "SIDE_UNKNOWN"
    assert row["token_id"] is None
    assert row["execution_allowed"] is False


def test_duplicate_seed_is_updated_not_recreated(postgres_test_schema) -> None:
    setup_proactive_seed_source("market-stage4-dupe", direction="YES", token_side_state="SIDE_DIRECTIONAL_YES")
    service = ProactiveCandidateGenerationService()

    service.refresh(force=True, limit=10, blocked_sample_limit=0)
    service.refresh(force=True, limit=10, blocked_sample_limit=0)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM proactive_candidate_seeds WHERE market_id='market-stage4-dupe'").fetchone()["count"]
    assert count == 1
