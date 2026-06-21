from datetime import UTC, datetime

from app.services.research_priority_watchlist import CADENCE_BY_BAND, build_priority_profile
from app.services.source_refresh_orchestrator import SOURCE_REFRESH_REGISTRY


def test_refresh_cadence_is_assigned_by_band():
    now = datetime(2026, 6, 18, tzinfo=UTC)
    high = build_priority_profile(
        {
            "market_memory_id": "m1",
            "market_id": "market_1",
            "status": "ACTIVE",
            "identity_verification_state": "VERIFIED",
            "token_verification_state": "TOKENS_VERIFIED",
            "freshness_state": "FRESH",
            "liquidity": 1000,
            "spread": 0.01,
            "volume": 2000,
            "recent_direct_event_count": 1,
            "recent_revalidation_count": 1,
            "recent_candidate_seed_count": 1,
        },
        now=now,
    )
    assert high["priority_band"] == "HIGH"
    assert high["refresh_cadence_seconds"] == CADENCE_BY_BAND["HIGH"]
    assert high["next_refresh_due_at"] is not None
    assert high["scheduler_state"] == "NOT_DUE"


def test_due_scheduler_registration_is_data_only_and_recommendation_based():
    registration = next(reg for reg in SOURCE_REFRESH_REGISTRY if reg.source_name == "research_priority_watchlist")
    assert registration.source_type == "RESEARCH_PRIORITY"
    assert registration.safe_to_refresh_data_only is True
    assert registration.table_name == "research_priority_watchlist"
    assert registration.candidate_scoped_supported is False
    assert registration.directional_supported is False


def test_archived_market_has_no_active_refresh_due():
    profile = build_priority_profile(
        {
            "market_memory_id": "m2",
            "market_id": "market_2",
            "status": "CLOSED",
            "identity_verification_state": "VERIFIED",
            "token_verification_state": "TOKENS_VERIFIED",
            "freshness_state": "FRESH",
        },
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "ARCHIVED"
    assert profile["next_refresh_due_at"] is None
    assert profile["scheduler_state"] == "ARCHIVED"
