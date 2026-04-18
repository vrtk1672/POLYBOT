from datetime import UTC, datetime, timedelta

from app.models.market import NormalizedMarket
from app.scoring.opportunity_score import OpportunityScorer


def build_market(**overrides) -> NormalizedMarket:
    now = datetime.now(UTC)
    data = {
        "market_id": "1",
        "event_id": "10",
        "event_title": "Event",
        "question": "Will POLYBOT work?",
        "slug": "will-polybot-work",
        "end_time": now + timedelta(days=3),
        "yes_price": 0.42,
        "no_price": 0.58,
        "last_trade_price": 0.42,
        "best_bid": 0.41,
        "best_ask": 0.43,
        "spread": 0.02,
        "liquidity": 120_000,
        "volume": 900_000,
        "volume_24h": 80_000,
        "open_interest": 50_000,
        "comment_count": 120,
        "competitive": 0.8,
        "accepting_orders": True,
        "updated_at": now - timedelta(minutes=30),
        "raw_market": {},
    }
    data.update(overrides)
    return NormalizedMarket(**data)


def test_scoring_prefers_active_balanced_liquid_market() -> None:
    scorer = OpportunityScorer()

    strong_market = build_market()
    weak_market = build_market(
        market_id="2",
        yes_price=0.98,
        no_price=0.02,
        last_trade_price=0.98,
        liquidity=1_500,
        volume=6_000,
        volume_24h=150,
        comment_count=1,
        end_time=datetime.now(UTC) + timedelta(days=120),
        updated_at=datetime.now(UTC) - timedelta(days=5),
    )

    strong_score = scorer.score_market(strong_market)
    weak_score = scorer.score_market(weak_market)

    assert strong_score.score > weak_score.score
    assert 0 <= strong_score.score <= 100
    assert strong_score.breakdown.price_attractiveness > weak_score.breakdown.price_attractiveness
    assert strong_score.reason


def test_scoring_handles_missing_optional_fields() -> None:
    scorer = OpportunityScorer()
    sparse_market = build_market(
        yes_price=None,
        no_price=None,
        last_trade_price=None,
        liquidity=None,
        volume=None,
        volume_24h=None,
        comment_count=None,
        updated_at=None,
    )

    result = scorer.score_market(sparse_market)

    assert 0 <= result.score <= 100
    assert result.reason
