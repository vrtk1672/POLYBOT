from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.moonshot_basket_engine import MoonshotBasketEngine


def test_moonshot_uses_basket_sizing_and_rejects_oversized_or_nonconvex():
    payload = StrategyRouteInput(market_id="m", opportunity_score=0.7, opportunity_components={"confidence": 0.6, "convexity": 0.9, "risk_penalty": 0.2, "wording_risk": 0.1, "liquidity_quality": 0.4, "capital_allowed": True})
    decision = MoonshotBasketEngine().evaluate(payload)
    assert decision.eligible is True
    assert decision.contract.position_sizing_rules["basket_sizing"] is True
    assert decision.contract.max_position_size_usd <= 25
    flat = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "convexity": 0.2}})
    assert MoonshotBasketEngine().evaluate(flat).rejection_reason == "moonshot_requires_extreme_convexity"

