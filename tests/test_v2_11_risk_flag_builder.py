from app.opportunity.contracts import OpportunityInput
from app.opportunity.risk_flag_builder import OpportunityRiskFlagBuilder


def test_risk_flags_capture_hard_blocks_and_ai_boundary():
    payload = OpportunityInput(
        market_id="m1",
        context_output={"risks": ["ai_cannot_override_risk"], "risk_score": 0.7},
        capital_output={"capital_allowed": False, "block_reason": "cash_reserve_too_low"},
        technical_truth={"technical_blocked": True, "block_reasons": ["missing_bid_ask"]},
    )

    flags = OpportunityRiskFlagBuilder().build(payload)
    names = {flag.risk_flag for flag in flags}

    assert "capital_not_allowed" in names
    assert "missing_bid_ask" in names
    assert "ai_cannot_override_risk" in names
    assert any(flag.blocks_opportunity for flag in flags)

