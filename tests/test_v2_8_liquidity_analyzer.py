from app.market_neuron.liquidity_analyzer import LiquidityAnalyzer
from app.market_neuron.orderbook_analyzer import OrderbookAnalyzer


def test_liquidity_analyzer_computes_fill_slippage_exit_quality_and_size():
    ob = OrderbookAnalyzer().analyze("m1", raw_orderbook={"bids": [[0.41, 1000]], "asks": [[0.42, 1200]]})
    liq = LiquidityAnalyzer().analyze(ob, target_size_usd=100)
    assert liq.expected_fill_score > 0
    assert liq.expected_slippage_bps >= 0
    assert liq.exit_quality_score > 0
    assert liq.max_safe_size_usd > 0


def test_liquidity_blocks_missing_exit_and_low_depth():
    missing = OrderbookAnalyzer().analyze("m1", raw_orderbook={})
    assert LiquidityAnalyzer().analyze(missing).block_reason == "missing_exit_liquidity"
    low_depth = OrderbookAnalyzer().analyze("m1", raw_orderbook={"bids": [[0.41, 10]], "asks": [[0.42, 10]]})
    assert LiquidityAnalyzer().analyze(low_depth).block_reason in {"low_exit_depth", "poor_exit_liquidity"}

