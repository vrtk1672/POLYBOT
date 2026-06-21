from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.no_trade_engine import NoTradeEngine


def test_no_trade_valid_always():
    decision = NoTradeEngine().evaluate(StrategyRouteInput(market_id="m"))
    assert decision.eligible is True
    assert decision.contract.engine == "NO_TRADE"
    assert decision.contract.max_position_size_usd == 0

