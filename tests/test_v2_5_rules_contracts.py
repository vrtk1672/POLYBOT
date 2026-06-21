from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.rules_neuron.contracts import ComplianceDecision, ParsedRules, RulesAnalysisResult, RulesInput, WordingRiskScore


def test_rules_contracts_validate_and_bound_scores() -> None:
    input_model = RulesInput(market_id="m1", rules_text="Resolve by official source.")
    assert input_model.market_id == "m1"
    parsed = ParsedRules(market_id="m1", rules_text_present=True)
    assert parsed.rules_text_present is True
    wording = WordingRiskScore(market_id="m1", total_wording_risk=2)
    assert wording.total_wording_risk == 1.0
    decision = ComplianceDecision(market_id="m1")
    assert decision.recommendation == "REVIEW_REQUIRED"
    result = RulesAnalysisResult(market_id="m1", wording_risk=0.72, dispute_risk=0.44, resolution_clarity=0.38, dangerous_edge_cases=["deadline unclear"], recommendation="NO_TRADE")
    assert result.signal()["recommendation"] == "NO_TRADE"


def test_rules_result_has_no_trading_execution_fields() -> None:
    result = RulesAnalysisResult(market_id="m1")
    dumped = result.model_dump()
    assert "order" not in dumped
    with pytest.raises(ValidationError):
        RulesAnalysisResult(market_id="m1", order_intent={"side": "buy"})

