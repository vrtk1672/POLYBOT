from app.opportunity.candidate_engine_suggester import CandidateEngineSuggester
from app.opportunity.contracts import OpportunityInput, OpportunityRiskFlag


def test_candidate_engines_are_suggestions_only_and_blocks_return_no_trade():
    suggester = CandidateEngineSuggester()
    blocked = suggester.suggest(OpportunityInput(market_id="m1"), score=0.9, risk_flags=[OpportunityRiskFlag(risk_flag="missing_bid_ask", severity="BLOCKING")])
    open_suggestions = suggester.suggest(
        OpportunityInput(
            market_id="m1",
            context_output={"strength": 0.8, "confidence": 0.8, "urgency_score": 0.8},
            technical_truth={"liquidity_signal": {"exit_quality_score": 0.8, "max_safe_size_usd": 1000}},
            market_memory={"wording_risk_avg": 0.1},
        ),
        score=0.7,
        risk_flags=[],
    )

    assert blocked == ["NO_TRADE"]
    assert "STRIKE" in open_suggestions
    assert "NO_TRADE" not in open_suggestions

