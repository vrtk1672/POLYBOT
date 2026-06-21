from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.news_neuron.contracts import (
    NewsDirection,
    NewsImpactScore,
    NewsMarketLink,
    NewsSignal,
    NewsSource,
    NewsSourceType,
    NormalizedNewsEvent,
    RawNewsEvent,
)


def test_news_contracts_validate_and_bound_scores() -> None:
    source = NewsSource(source_id="manual", name="Manual", source_type=NewsSourceType.MANUAL, reliability_score=5)
    assert source.reliability_score == 1.0
    raw = RawNewsEvent(source_id="manual", title="Breaking BTC headline")
    assert raw.content_hash
    normalized = NormalizedNewsEvent(source_id="manual", title=raw.title, normalized_title="breaking btc headline", importance_score=2)
    assert normalized.importance_score == 1.0
    link = NewsMarketLink(news_event_id=normalized.news_event_id, market_id="m1", link_score=2, direction=NewsDirection.UNKNOWN, confidence=2)
    assert link.link_score == 1.0
    impact = NewsImpactScore(news_event_id=normalized.news_event_id, market_id="m1", strength=2, confidence=2, urgency=2, ttl_seconds=60)
    assert impact.signal["node"] == "news"
    assert impact.signal["strength"] == 1.0


def test_news_signal_rejects_invalid_direction_and_trade_fields() -> None:
    with pytest.raises(ValidationError):
        NewsSignal(market_id="m1", direction="MAYBE")
    with pytest.raises(ValidationError):
        NewsSignal(market_id="m1", direction="YES", order_intent={"side": "buy"})

