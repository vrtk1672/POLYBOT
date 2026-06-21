from app.strategy.contracts import StrategyRouteInput
from app.strategy.engines.maker_engine import MakerEngine


def test_maker_requires_spread_depth_and_orderbook_truth():
    payload = StrategyRouteInput(market_id="m", opportunity_score=0.7, opportunity_components={"confidence": 0.8, "liquidity_quality": 0.8, "fee_reward_advantage": 0.5, "adverse_selection_risk": 0.1, "capital_allowed": True}, technical_truth={"orderbook_signal": {"has_bid_ask": True, "depth_2c": 800}})
    assert MakerEngine().evaluate(payload).eligible is True
    missing = payload.model_copy(update={"technical_truth": {"orderbook_signal": {"has_bid_ask": False, "depth_2c": 800}}})
    assert MakerEngine().evaluate(missing).rejection_reason == "maker_requires_orderbook_truth"
    shallow = payload.model_copy(update={"technical_truth": {"orderbook_signal": {"has_bid_ask": True, "depth_2c": 10}}})
    assert MakerEngine().evaluate(shallow).rejection_reason == "maker_requires_spread_depth"

