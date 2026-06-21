from datetime import UTC, datetime

from app.services.research_priority_watchlist import build_priority_profile


def test_watchlist_profile_contains_required_data_only_fields():
    profile = build_priority_profile(
        {
            "market_memory_id": "memory_watch",
            "market_id": "market_watch",
            "condition_id": "condition_watch",
            "status": "ACTIVE",
            "identity_verification_state": "VERIFIED",
            "token_verification_state": "TOKENS_VERIFIED",
            "freshness_state": "FRESH",
            "liquidity": 750,
            "spread": 0.03,
            "volume": 1200,
            "recent_likely_event_count": 1,
            "recent_revalidation_count": 1,
            "recent_candidate_seed_count": 1,
            "recent_yes_seed_count": 1,
            "recent_no_seed_count": 0,
            "best_opportunity_score": 62.0,
        },
        run_id="run_1",
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["research_watchlist_id"].startswith("research_watchlist_")
    assert profile["priority_run_id"] == "run_1"
    assert profile["market_id"] == "market_watch"
    assert profile["recent_candidate_seed_count"] == 1
    assert profile["recent_yes_seed_count"] == 1
    assert profile["best_opportunity_score"] == 62.0
    assert profile["score_components_json"]
    assert profile["evidence_inputs_json"]["market_id"] == "market_watch"


def test_priority_unknown_inputs_do_not_fake_high_priority():
    profile = build_priority_profile(
        {
            "market_memory_id": "memory_unknown",
            "market_id": "market_unknown",
            "status": "UNRESOLVED",
            "identity_verification_state": "UNRESOLVED",
            "token_verification_state": "TOKENS_MISSING",
            "freshness_state": "NEEDS_REFRESH",
        },
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] in {"LOW", "DORMANT"}
    assert profile["priority_score"] == 0
    assert "TOKENS_MISSING" in profile["demotion_reasons_json"]


def test_watchlist_refresh_profile_does_not_grant_execution():
    profile = build_priority_profile(
        {
            "market_memory_id": "memory_exec",
            "market_id": "market_exec",
            "status": "ACTIVE",
            "identity_verification_state": "VERIFIED",
            "token_verification_state": "TOKENS_VERIFIED",
            "freshness_state": "FRESH",
            "liquidity": 1000,
            "spread": 0.01,
            "volume": 10000,
            "recent_direct_event_count": 2,
            "recent_candidate_seed_count": 2,
            "paper_observation_interest_count": 2,
        },
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "HIGH"
    assert "execution_allowed" not in profile
    assert "paper_allowed" not in profile
    assert "live_allowed" not in profile
