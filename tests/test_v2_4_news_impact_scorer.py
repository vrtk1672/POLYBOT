from __future__ import annotations

from app.news_neuron.contracts import NewsMarketLink, NormalizedNewsEvent
from app.news_neuron.impact_scorer import NewsImpactScorer


def test_impact_score_bounded_and_signal_shape(monkeypatch) -> None:
    scorer = NewsImpactScorer()
    monkeypatch.setattr(scorer, "_get_market", lambda market_id: {"market_id": market_id, "closed": False})
    monkeypatch.setattr(scorer, "_get_latest_snapshot", lambda market_id: {"data_completeness_score": 90, "stale": False})
    monkeypatch.setattr(scorer._priced_in, "detect_already_priced_in", lambda event, market_id: {"score": 0.1, "risk_flags": [], "reason": "test"})
    event = NormalizedNewsEvent(source_id="manual", title="Breaking BTC news", normalized_title="breaking btc news", importance_score=0.9, urgency_score=0.8, source_reliability=0.8)
    link = NewsMarketLink(news_event_id=event.news_event_id, market_id="m1", link_score=0.9, confidence=0.8)
    impact = scorer.score_news_impact(event, link)
    assert impact.strength > 0.5
    assert impact.confidence > 0.5
    assert impact.signal["node"] == "news"


def test_low_source_reliability_stale_market_missing_data_lowers_confidence(monkeypatch) -> None:
    scorer = NewsImpactScorer()
    monkeypatch.setattr(scorer, "_get_market", lambda market_id: {"market_id": market_id, "closed": True})
    monkeypatch.setattr(scorer, "_get_latest_snapshot", lambda market_id: {"data_completeness_score": 20, "stale": True})
    event = NormalizedNewsEvent(source_id="manual", title="BTC news", normalized_title="btc news", importance_score=0.9, source_reliability=0.2)
    link = NewsMarketLink(news_event_id=event.news_event_id, market_id="m1", link_score=0.9, confidence=0.9)
    impact = scorer.score_news_impact(event, link)
    assert impact.confidence < 0.2
    assert "low_data_completeness" in impact.risk_flags

