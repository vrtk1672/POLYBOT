from __future__ import annotations

from app.social_neuron.contracts import RawSocialEvent
from app.social_neuron.normalizer import SocialNormalizer


def test_raw_event_normalized_with_tags_entities_and_scores() -> None:
    normalizer = SocialNormalizer()
    event = normalizer.normalize_raw_event(RawSocialEvent(source_id="manual", text="BTC traders watch $BTC breakout #Crypto", engagement={"likes": 100, "followers": 1000}))
    assert event.normalized_text == "btc traders watch $btc breakout #crypto"
    assert "crypto" in event.hashtags
    assert "BTC" in event.cashtags
    assert "crypto" in event.category
    assert event.engagement_score > 0
    assert event.influence_score > 0
