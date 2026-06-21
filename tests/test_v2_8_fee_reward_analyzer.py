from app.market_neuron.fee_reward_analyzer import FeeRewardAnalyzer
from app.market_neuron.liquidity_analyzer import LiquidityAnalyzer
from app.market_neuron.orderbook_analyzer import OrderbookAnalyzer


def test_fee_reward_analyzer_reduces_net_edge_after_costs():
    ob = OrderbookAnalyzer().analyze("m1", raw_orderbook={"bids": [[0.41, 1000]], "asks": [[0.42, 1000]]})
    liq = LiquidityAnalyzer().analyze(ob)
    low = FeeRewardAnalyzer().analyze(ob, liq, fee_snapshot={"maker_cost_bps": 1, "taker_cost_bps": 2}, edge_reference=0.05)
    high = FeeRewardAnalyzer().analyze(ob, liq, fee_snapshot={"maker_cost_bps": 100, "taker_cost_bps": 100, "slippage_cost_bps": 100}, edge_reference=0.05)
    assert high.net_edge_after_costs < low.net_edge_after_costs
    assert high.friction_score > low.friction_score


def test_rewards_do_not_improve_score_when_orderbook_invalid():
    ob = OrderbookAnalyzer().analyze("m1", raw_orderbook={})
    liq = LiquidityAnalyzer().analyze(ob)
    signal = FeeRewardAnalyzer().analyze(ob, liq, fee_snapshot={"reward_pool_usd": 1_000_000})
    assert signal.reward_score == 0

