from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.convex_engine import ConvexEngine


def test_convex_requires_asymmetric_upside_and_defined_downside():
    payload = StrategyRouteInput(market_id="m", opportunity_score=0.7, opportunity_components={"confidence": 0.7, "convexity": 0.8, "risk_penalty": 0.2, "trap_risk": 0.1, "liquidity_quality": 0.5, "capital_allowed": True})
    assert ConvexEngine().evaluate(payload).eligible is True
    flat = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "convexity": 0.2}})
    assert ConvexEngine().evaluate(flat).rejection_reason == "convex_requires_asymmetric_upside"
    undefined = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "risk_penalty": 0.9}})
    assert ConvexEngine().evaluate(undefined).rejection_reason == "convex_rejects_undefined_downside"

