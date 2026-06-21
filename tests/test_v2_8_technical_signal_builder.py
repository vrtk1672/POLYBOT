from datetime import UTC, datetime, timedelta

from app.market_neuron.fee_reward_analyzer import FeeRewardAnalyzer
from app.market_neuron.liquidity_analyzer import LiquidityAnalyzer
from app.market_neuron.market_analyzer import MarketAnalyzer
from app.market_neuron.orderbook_analyzer import OrderbookAnalyzer
from app.market_neuron.technical_signal_builder import TechnicalSignalBuilder
from app.market_neuron.time_analyzer import TimeAnalyzer


def test_builder_blocks_missing_orderbook_and_liquidity_and_short_ttl_does_not_override():
    market = MarketAnalyzer().analyze("m1", [{"current_price_yes": 0.5, "snapshot_at": datetime.now(UTC), "data_completeness_score": 1.0}])
    ob = OrderbookAnalyzer().analyze("m1", raw_orderbook={})
    liq = LiquidityAnalyzer().analyze(ob)
    time = TimeAnalyzer().analyze("m1", market_close_time=datetime.now(UTC) + timedelta(minutes=5))
    fees = FeeRewardAnalyzer().analyze(ob, liq)
    truth = TechnicalSignalBuilder().build_truth(market, ob, liq, time, fees)
    assert truth.technical_blocked is True
    assert "missing_bid_ask" in truth.block_reasons
    assert "missing_exit_liquidity" in truth.block_reasons
    assert truth.time_signal.urgency_score > 0.9
    assert truth.technical_score <= 0.25

