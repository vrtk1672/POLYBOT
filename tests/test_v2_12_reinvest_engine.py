from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.reinvest_engine import ReinvestEngine


def test_reinvest_is_metadata_only_and_does_not_mutate_capital():
    decision = ReinvestEngine().evaluate(StrategyRouteInput(market_id="m"))
    assert decision.eligible is False
    assert decision.rejection_reason == "reinvest_requires_v2_13_profit_pocket"
    assert decision.contract is None

