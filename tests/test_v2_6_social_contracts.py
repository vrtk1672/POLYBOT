from __future__ import annotations

import pytest

from app.social_neuron.contracts import (
    NormalizedSocialEvent,
    RawSocialEvent,
    SocialPlatform,
    SocialSentiment,
    SocialSignal,
    SocialSource,
    SocialSourceType,
)


def test_social_contracts_validate_and_bound_scores() -> None:
    source = SocialSource(source_id="manual", name="Manual", source_type=SocialSourceType.MANUAL, platform=SocialPlatform.MANUAL, reliability_score=2)
    raw = RawSocialEvent(source_id="manual", platform=SocialPlatform.MANUAL, text="BTC is moving fast #BTC")
    event = NormalizedSocialEvent(source_id="manual", platform=SocialPlatform.MANUAL, text=raw.text, normalized_text="btc is moving fast", engagement_score=2)
    signal = SocialSignal(market_id="m1", hype_pressure=2, sentiment=SocialSentiment.YES, mentions_velocity=3.4, bot_risk=-1, confidence=2)
    assert source.reliability_score == 1
    assert raw.content_hash
    assert event.engagement_score == 1
    assert signal.hype_pressure == 1
    assert signal.bot_risk == 0
    assert "order" not in signal.model_dump()


def test_invalid_sentiment_rejected() -> None:
    with pytest.raises(ValueError):
        SocialSignal(market_id="m1", sentiment="TRADE_NOW")
