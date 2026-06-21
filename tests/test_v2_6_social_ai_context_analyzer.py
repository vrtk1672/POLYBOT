from __future__ import annotations

from app.social_neuron.ai_context_analyzer import SocialAIContextAnalyzer
from app.social_neuron.contracts import NormalizedSocialEvent, SocialHypeScore, SocialMarketLink


class _FakeAI:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request):
        self.calls += 1
        return {"status": "LOCAL_COMPLETED", "structured_output": {"summary": "ok"}, "trade_fields": []}


def test_ai_analysis_optional_unavailable_and_no_trade_fields() -> None:
    event = NormalizedSocialEvent(source_id="manual", text="BTC hype", normalized_text="btc hype")
    link = SocialMarketLink(social_event_id=event.social_event_id, market_id="m1", link_score=0.8, confidence=0.8)
    low = SocialHypeScore(market_id="m1", confidence=0.1)
    analyzer = SocialAIContextAnalyzer(ai_service=_FakeAI())
    assert analyzer.analyze_social_context(event, link, low)["status"] == "SKIPPED"
    result = analyzer.analyze_social_context(event, link, SocialHypeScore(market_id="m1", hype_pressure=0.8, confidence=0.8))
    assert "order_intent" not in str(result).lower()
