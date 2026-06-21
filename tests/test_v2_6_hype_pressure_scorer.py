from __future__ import annotations

from app.social_neuron.contracts import SocialNarrative, SocialSentiment, SocialSentimentScore
from app.social_neuron.hype_pressure_scorer import HypePressureScorer


def test_hype_score_bounded_and_bot_risk_lowers_confidence(monkeypatch) -> None:
    scorer = HypePressureScorer()
    monkeypatch.setattr(scorer._velocity, "compute_mentions_velocity", lambda market_id, window_seconds: {"mention_count": 20, "unique_author_count": 10, "mentions_velocity": 4.0, "spam_ratio": 0.1, "velocity_zscore": 3.0})
    good = scorer.score_hype_pressure("m1", sentiment_score=SocialSentimentScore(social_event_id="s1", sentiment=SocialSentiment.YES, confidence=0.8), narrative=SocialNarrative(narrative_key="n", title="BTC", narrative_strength=0.8))
    monkeypatch.setattr(scorer._velocity, "compute_mentions_velocity", lambda market_id, window_seconds: {"mention_count": 20, "unique_author_count": 2, "mentions_velocity": 4.0, "spam_ratio": 0.9, "velocity_zscore": 3.0})
    bad = scorer.score_hype_pressure("m1", sentiment_score=SocialSentimentScore(social_event_id="s1", sentiment=SocialSentiment.YES, confidence=0.8), narrative=SocialNarrative(narrative_key="n", title="BTC", narrative_strength=0.8))
    assert 0 <= good.hype_pressure <= 1
    assert good.confidence > bad.confidence
    assert good.signal["node"] == "social"
