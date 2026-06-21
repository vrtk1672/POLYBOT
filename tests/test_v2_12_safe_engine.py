from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.safe_engine import SafeEngine


def test_safe_only_near_certainty_and_rejects_high_wording_risk():
    payload = StrategyRouteInput(market_id="m", opportunity_score=0.75, opportunity_components={"confidence": 0.85, "liquidity_quality": 0.82, "exit_probability": 0.83, "wording_risk": 0.05, "capital_allowed": True})
    assert SafeEngine().evaluate(payload).eligible is True
    risky = payload.model_copy(update={"opportunity_components": {**payload.opportunity_components, "wording_risk": 0.6}})
    decision = SafeEngine().evaluate(risky)
    assert decision.eligible is False
    assert decision.rejection_reason == "safe_rejects_high_wording_risk"

