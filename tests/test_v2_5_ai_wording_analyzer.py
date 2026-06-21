from __future__ import annotations

from app.ai_brain.contracts import AIResponse, AITaskType
from app.rules_neuron.ai_wording_analyzer import AIWordingAnalyzer
from app.rules_neuron.contracts import RulesAnalysisResult, RulesInput


class FakeAI:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request, *, allow_cloud: bool, reason: str):
        self.calls += 1
        assert allow_cloud is False
        return AIResponse(ai_request_id="ai1", task_type=AITaskType.WORDING_RISK_PRECHECK, model_name="fake", structured_output={"risk": "review"}, confidence=0.7, risk_flags=["wording"])


def test_mocked_ai_analysis_and_cloud_blocked_by_default() -> None:
    fake = FakeAI()
    analyzer = AIWordingAnalyzer(ai_service=fake)
    result = analyzer.analyze_wording_with_ai(RulesInput(market_id="m1", rules_text="ambiguous but present"), RulesAnalysisResult(market_id="m1", wording_risk=0.4, recommendation="REVIEW_REQUIRED"))
    assert result["status"] == "COMPLETED"
    assert fake.calls == 1


def test_ai_cannot_override_obvious_compliance_block() -> None:
    fake = FakeAI()
    analyzer = AIWordingAnalyzer(ai_service=fake)
    result = analyzer.analyze_wording_with_ai(RulesInput(market_id="m1"), RulesAnalysisResult(market_id="m1", wording_risk=0.9, recommendation="NO_TRADE"))
    assert result["status"] == "SKIPPED"
    assert fake.calls == 0

