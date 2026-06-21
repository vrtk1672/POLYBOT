from app.opportunity.contracts import OpportunityRiskFlag
from app.opportunity.no_trade_reason_builder import NoTradeReasonBuilder


def test_no_trade_reasons_are_generated_from_flags_and_weakness():
    reasons = NoTradeReasonBuilder().build(
        score=0.1,
        confidence=0.1,
        risk_flags=[OpportunityRiskFlag(risk_flag="capital_not_allowed", severity="BLOCKING"), OpportunityRiskFlag(risk_flag="wide_spread", penalty=0.5)],
        weak_trigger=True,
    )

    assert "capital_not_allowed" in reasons
    assert "wide_spread" in reasons
    assert "weak_trigger" in reasons
    assert "low_context_confidence" in reasons

