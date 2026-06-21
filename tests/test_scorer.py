"""Tests for gamma_crawler.py derived scoring metrics.

Validates that edge_cents, liquidity_bucket, and hours_remaining
return correct values, and that the full score + rank pipeline
orders markets as expected.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.market import NormalizedMarket
from app.scoring.opportunity_score import OpportunityScorer
from gamma_crawler import edge_cents, hours_remaining, liquidity_bucket, score_and_rank


def _market(**overrides) -> NormalizedMarket:
    now = datetime.now(UTC)
    defaults = {
        "market_id": "test-1",
        "event_id": "evt-1",
        "event_title": "Test Event",
        "question": "Will this test pass?",
        "end_time": now + timedelta(days=3),
        "yes_price": 0.40,
        "no_price": 0.60,
        "last_trade_price": 0.40,
        "best_bid": 0.39,
        "best_ask": 0.41,
        "spread": 0.02,
        "liquidity": 50_000.0,
        "volume": 300_000.0,
        "volume_24h": 40_000.0,
        "comment_count": 80,
        "accepting_orders": True,
        "updated_at": now - timedelta(minutes=20),
        "raw_market": {},
    }
    defaults.update(overrides)
    return NormalizedMarket(**defaults)


# ---------------------------------------------------------------------------
# edge_cents
# ---------------------------------------------------------------------------

class TestEdgeCents:
    def test_yes_is_cheap_side(self) -> None:
        m = _market(yes_price=0.25, no_price=0.75)
        assert edge_cents(m) == 75  # 1 - 0.25 = 0.75 → 75 cents

    def test_no_is_cheap_side(self) -> None:
        m = _market(yes_price=0.80, no_price=0.20)
        assert edge_cents(m) == 80  # 1 - 0.20 = 0.80 → 80 cents

    def test_balanced_market(self) -> None:
        m = _market(yes_price=0.50, no_price=0.50)
        assert edge_cents(m) == 50

    def test_no_prices_returns_none(self) -> None:
        m = _market(yes_price=None, no_price=None)
        assert edge_cents(m) is None


# ---------------------------------------------------------------------------
# liquidity_bucket
# ---------------------------------------------------------------------------

class TestLiquidityBucket:
    def test_whale_by_liquidity(self) -> None:
        m = _market(liquidity=100_000.0, volume_24h=0.0)
        assert liquidity_bucket(m) == "whale"

    def test_whale_by_volume(self) -> None:
        m = _market(liquidity=0.0, volume_24h=200_000.0)
        assert liquidity_bucket(m) == "whale"

    def test_high_by_liquidity(self) -> None:
        m = _market(liquidity=15_000.0, volume_24h=0.0)
        assert liquidity_bucket(m) == "high"

    def test_high_by_volume(self) -> None:
        m = _market(liquidity=0.0, volume_24h=50_000.0)
        assert liquidity_bucket(m) == "high"

    def test_safe(self) -> None:
        m = _market(liquidity=500.0, volume_24h=200.0)
        assert liquidity_bucket(m) == "safe"

    def test_none_values_treated_as_zero(self) -> None:
        m = _market(liquidity=None, volume_24h=None)
        assert liquidity_bucket(m) == "safe"


# ---------------------------------------------------------------------------
# hours_remaining
# ---------------------------------------------------------------------------

class TestHoursRemaining:
    def test_future_end_time(self) -> None:
        m = _market(end_time=datetime.now(UTC) + timedelta(hours=12))
        h = hours_remaining(m)
        assert h is not None
        assert 11.9 < h < 12.1

    def test_past_end_time_returns_zero(self) -> None:
        m = _market(end_time=datetime.now(UTC) - timedelta(hours=1))
        h = hours_remaining(m)
        assert h == 0.0

    def test_no_end_time_returns_none(self) -> None:
        m = _market(end_time=None)
        assert hours_remaining(m) is None


# ---------------------------------------------------------------------------
# Full pipeline: score_and_rank
# ---------------------------------------------------------------------------

class TestScoreAndRank:
    def test_returns_sorted_descending(self) -> None:
        now = datetime.now(UTC)
        strong = _market(
            market_id="strong",
            yes_price=0.40, no_price=0.60,
            liquidity=150_000.0, volume_24h=90_000.0,
            end_time=now + timedelta(days=4),
            updated_at=now - timedelta(minutes=10),
        )
        weak = _market(
            market_id="weak",
            yes_price=0.97, no_price=0.03,
            liquidity=800.0, volume_24h=50.0,
            end_time=now + timedelta(days=200),
            updated_at=now - timedelta(days=10),
        )
        ranked = score_and_rank([weak, strong])
        assert len(ranked) == 2
        assert ranked[0].market.market_id == "strong"
        assert ranked[0].score > ranked[1].score

    def test_scores_within_valid_range(self) -> None:
        markets = [
            _market(market_id=str(i), yes_price=round(0.1 * i, 1))
            for i in range(1, 10)
        ]
        ranked = score_and_rank(markets)
        for item in ranked:
            assert 0.0 <= item.score <= 100.0

    def test_empty_input(self) -> None:
        assert score_and_rank([]) == []
