from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.hunt_engine import HuntEngine


def test_hunt_requires_chaos_and_governor_approval():
    payload = StrategyRouteInput(market_id="m", hunt_approval=True, opportunity_score=0.8, opportunity_components={"confidence": 0.8, "trigger_strength": 0.85, "time_efficiency": 0.85, "repricing_potential": 0.85, "exit_probability": 0.7, "capital_allowed": True})
    assert HuntEngine().evaluate(payload).eligible is True
    no_approval = payload.model_copy(update={"hunt_approval": False})
    decision = HuntEngine().evaluate(no_approval)
    assert decision.eligible is False
    assert decision.rejection_reason == "hunt_requires_governor_approval"

