from app.whale_neuron.ai_context_analyzer import WhaleAIContextAnalyzer
from app.whale_neuron.contracts import WhaleEvent, WhaleProfile


class FakeAI:
    def __init__(self):
        self.calls = 0

    def analyze(self, request, **kwargs):
        self.calls += 1
        return {"status": "OK", "structured_output": {"summary": "watch only"}}


def test_ai_context_analyzer_optional_and_no_trade_fields():
    fake = FakeAI()
    analyzer = WhaleAIContextAnalyzer(ai_service=fake)
    result = analyzer.analyze_whale_context(WhaleEvent(source_id="manual", market_id="m", confidence=0.2), WhaleProfile(whale_id="w"), allow_cloud=True)
    assert result["status"] == "OK"
    assert fake.calls == 1
    assert "order" not in str(result).lower()

