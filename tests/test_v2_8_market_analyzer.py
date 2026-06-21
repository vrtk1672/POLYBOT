from datetime import UTC, datetime, timedelta

from app.market_neuron.contracts import MarketRegime, TrendDirection
from app.market_neuron.market_analyzer import MarketAnalyzer


def test_market_analyzer_computes_price_change_momentum_volatility_trend_and_regime():
    now = datetime.now(UTC)
    rows = [
        {"market_id": "m1", "current_price_yes": 0.40, "snapshot_at": now - timedelta(minutes=20), "data_completeness_score": 0.9, "liquidity": 1000},
        {"market_id": "m1", "current_price_yes": 0.47, "snapshot_at": now - timedelta(minutes=5), "data_completeness_score": 0.9, "liquidity": 1000},
        {"market_id": "m1", "current_price_yes": 0.52, "snapshot_at": now, "data_completeness_score": 0.9, "liquidity": 1000, "volume_1h": 50},
    ]
    signal = MarketAnalyzer().analyze("m1", rows)
    assert signal.price_change_5m > 0
    assert signal.momentum_score > 0
    assert signal.volatility_score >= 0
    assert signal.trend_direction == TrendDirection.UP
    assert signal.market_regime in {MarketRegime.TRENDING, MarketRegime.VOLATILE, MarketRegime.CHAOTIC}


def test_missing_market_snapshot_is_stale_and_blocked():
    signal = MarketAnalyzer().analyze("missing", [])
    assert signal.stale is True
    assert signal.block_reason == "missing_market_snapshot"

