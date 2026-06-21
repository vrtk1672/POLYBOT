from datetime import UTC, datetime, timedelta

from app.services.research_priority_watchlist import build_priority_profile, priority_formula


def _base(**overrides):
    row = {
        "market_memory_id": "memory_1",
        "market_id": "market_1",
        "condition_id": "condition_1",
        "status": "ACTIVE",
        "identity_verification_state": "VERIFIED",
        "token_verification_state": "TOKENS_VERIFIED",
        "freshness_state": "FRESH",
        "liquidity": 500,
        "spread": 0.02,
        "volume": 1000,
        "close_time": datetime(2026, 6, 20, tzinfo=UTC),
        "recent_direct_event_count": 0,
        "recent_likely_event_count": 0,
        "recent_revalidation_count": 0,
        "recent_candidate_seed_count": 0,
        "recent_yes_seed_count": 0,
        "recent_no_seed_count": 0,
        "best_opportunity_score": None,
        "paper_observation_interest_count": 0,
        "full_paper_ready_count": 0,
    }
    row.update(overrides)
    return row


def test_active_market_with_fresh_direct_event_becomes_high():
    profile = build_priority_profile(
        _base(recent_direct_event_count=1, recent_revalidation_count=1),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "HIGH"
    assert profile["priority_score"] >= 60
    assert "RECENT_STRONG_EVENT_LINKS" in profile["priority_reasons_json"]


def test_candidate_seed_boosts_priority():
    profile = build_priority_profile(
        _base(recent_candidate_seed_count=1, recent_revalidation_count=1),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] in {"HIGH", "MEDIUM"}
    assert "RECENT_PROACTIVE_CANDIDATE_SEEDS" in profile["priority_reasons_json"]


def test_paper_observation_interest_boosts_priority_without_execution_authority():
    profile = build_priority_profile(
        _base(paper_observation_interest_count=1, recent_likely_event_count=1),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["score_components_json"]["paper_observation_interest_component"] > 0
    assert profile["priority_band"] in {"HIGH", "MEDIUM"}


def test_good_liquidity_tight_spread_and_closing_soon_boost_score():
    now = datetime(2026, 6, 18, tzinfo=UTC)
    profile = build_priority_profile(
        _base(close_time=now + timedelta(days=2), recent_likely_event_count=1),
        now=now,
    )
    components = profile["score_components_json"]
    assert components["liquidity_component"] == 10
    assert components["spread_component"] == 8
    assert components["closing_soon_component"] == 10


def test_low_liquidity_no_events_can_become_dormant():
    profile = build_priority_profile(
        _base(liquidity=0.01, spread=0.2, volume=0, close_time=None),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "DORMANT"
    assert "NO_RECENT_SIGNAL_HEAT" in profile["demotion_reasons_json"]


def test_closed_market_is_archived_not_deleted():
    profile = build_priority_profile(
        _base(status="RESOLVED", recent_direct_event_count=3),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "ARCHIVED"
    assert profile["refresh_cadence_seconds"] == 0
    assert profile["scheduler_state"] == "ARCHIVED"


def test_token_mismatch_demotes_priority():
    profile = build_priority_profile(
        _base(token_verification_state="TOKENS_MISMATCH", recent_direct_event_count=3),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert profile["priority_band"] == "LOW"
    assert "TOKENS_MISMATCH" in profile["demotion_reasons_json"]


def test_stale_identity_lowers_priority():
    clean = build_priority_profile(_base(recent_likely_event_count=1), now=datetime(2026, 6, 18, tzinfo=UTC))
    stale = build_priority_profile(
        _base(recent_likely_event_count=1, freshness_state="STALE", identity_verification_state="PARTIAL"),
        now=datetime(2026, 6, 18, tzinfo=UTC),
    )
    assert stale["priority_score"] < clean["priority_score"]
    assert "MARKET_MEMORY_STALE" in stale["demotion_reasons_json"]


def test_priority_score_is_deterministic():
    row = _base(recent_direct_event_count=1, best_opportunity_score=61.19)
    now = datetime(2026, 6, 18, tzinfo=UTC)
    assert build_priority_profile(row, now=now) == build_priority_profile(row, now=now)
    assert "priority_score =" in priority_formula()
