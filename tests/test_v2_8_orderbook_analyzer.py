from app.market_neuron.orderbook_analyzer import OrderbookAnalyzer


def test_orderbook_analyzer_computes_best_bid_ask_spread_depth_and_imbalance():
    signal = OrderbookAnalyzer().analyze(
        "m1",
        token_id="yes",
        side="YES",
        raw_orderbook={"bids": [{"price": 0.41, "size": 500}], "asks": [{"price": 0.43, "size": 700}]},
    )
    assert signal.best_bid == 0.41
    assert signal.best_ask == 0.43
    assert signal.spread_bps > 0
    assert signal.depth_2c == 1200
    assert signal.has_bid_ask is True
    assert 0 <= signal.imbalance_score <= 1


def test_orderbook_blocks_missing_bid_ask_and_wide_spread():
    missing = OrderbookAnalyzer().analyze("m1", raw_orderbook={"bids": [], "asks": []})
    assert missing.block_reason == "missing_bid_ask"
    wide = OrderbookAnalyzer().analyze("m1", raw_orderbook={"bids": [[0.30, 1000]], "asks": [[0.45, 1000]]})
    assert wide.block_reason == "wide_spread"

