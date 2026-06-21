from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.strike_engine import StrikeEngine


def test_strike_requires_trigger_and_rejects_already_priced_in():
    payload = StrategyRouteInput(market_id="m", opportunity_score=0.75, opportunity_components={"confidence": 0.8, "trigger_strength": 0.8, "repricing_potential": 0.75, "exit_probability": 0.7, "already_priced_in_score": 0.1, "capital_allowed": True}, context_output={"context_shift": True})
    assert StrikeEngine().evaluate(payload).eligible is True
    weak = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "trigger_strength": 0.2}})
    assert StrikeEngine().evaluate(weak).rejection_reason == "strike_requires_trigger"
    priced = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "already_priced_in_score": 0.8}})
    assert StrikeEngine().evaluate(priced).rejection_reason == "strike_rejects_already_priced_in"

