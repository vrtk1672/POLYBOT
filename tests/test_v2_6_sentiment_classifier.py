from __future__ import annotations

from app.social_neuron.contracts import NormalizedSocialEvent, SocialSentiment
from app.social_neuron.sentiment_classifier import SentimentClassifier


def test_sentiment_classifier_directional_and_unclear() -> None:
    classifier = SentimentClassifier()
    bullish = classifier.classify(NormalizedSocialEvent(source_id="manual", text="BTC bullish breakout", normalized_text="btc bullish breakout"))
    bearish = classifier.classify(NormalizedSocialEvent(source_id="manual", text="BTC bearish crash", normalized_text="btc bearish crash"))
    support = classifier.classify(NormalizedSocialEvent(source_id="manual", text="I support yes", normalized_text="i support yes"))
    unclear = classifier.classify(NormalizedSocialEvent(source_id="manual", text="watching this", normalized_text="watching this"))
    assert bullish.sentiment == SocialSentiment.BULLISH
    assert bearish.sentiment == SocialSentiment.BEARISH
    assert support.sentiment == SocialSentiment.YES
    assert unclear.sentiment in {SocialSentiment.UNKNOWN, SocialSentiment.NEUTRAL}
    assert 0 <= bullish.confidence <= 1
