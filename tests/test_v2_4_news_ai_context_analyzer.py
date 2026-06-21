from __future__ import annotations

from app.ai_brain.contracts import AIResponse, AITaskType
from app.news_neuron.ai_context_analyzer import NewsAIContextAnalyzer
from app.news_neuron.contracts import NewsImpactScore, NewsMarketLink, NormalizedNewsEvent


class FakeAI:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request, *, allow_cloud: bool, reason: str):
        self.calls += 1
        return AIResponse(
            ai_request_id="ai1",
            task_type=AITaskType.CONTEXT_SUMMARY,
            model_name="fake",
            structured_output={"summary": "safe"},
            confidence=0.8,
            risk_flags=[],
        )


def test_mocked_ai_analysis_is_optional_and_safe() -> None:
    fake = FakeAI()
    analyzer = NewsAIContextAnalyzer(ai_service=fake)
    event = NormalizedNewsEvent(source_id="manual", title="BTC", normalized_title="btc")
    link = NewsMarketLink(news_event_id=event.news_event_id, market_id="m1", link_score=0.8, confidence=0.8)
    impact = NewsImpactScore(news_event_id=event.news_event_id, market_id="m1", strength=0.8, confidence=0.8)
    result = analyzer.analyze_news_context(event, link, impact)
    assert result["status"] == "COMPLETED"
    assert fake.calls == 1
    assert "order_intent" not in str(result).lower()


def test_low_value_skips_ai_call() -> None:
    fake = FakeAI()
    analyzer = NewsAIContextAnalyzer(ai_service=fake)
    event = NormalizedNewsEvent(source_id="manual", title="BTC", normalized_title="btc")
    link = NewsMarketLink(news_event_id=event.news_event_id, market_id="m1", link_score=0.1, confidence=0.1)
    impact = NewsImpactScore(news_event_id=event.news_event_id, market_id="m1", strength=0.1, confidence=0.1)
    result = analyzer.analyze_news_context(event, link, impact)
    assert result["status"] == "SKIPPED"
    assert fake.calls == 0

