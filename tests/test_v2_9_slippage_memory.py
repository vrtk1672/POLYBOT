from app.market_memory.slippage_memory_builder import SlippageMemoryBuilder


def test_bad_slippage_updates_slippage_memory():
    memory = SlippageMemoryBuilder().build(
        [
            {"expected_slippage_bps": 50, "realized_slippage_bps": 120, "fill_failed": True, "spread_bps": 80, "depth_2c": 100, "depth_5c": 200},
            {"expected_slippage_bps": 70, "realized_slippage_bps": 160, "fill_failed": True, "spread_bps": 120, "depth_2c": 50, "depth_5c": 120},
        ],
        market_id="m1",
        market_family="crypto",
    )

    assert memory.avg_expected_slippage_bps == 60
    assert memory.avg_realized_slippage_bps == 140
    assert memory.slippage_error_bps == 80
    assert memory.failed_fill_rate == 1.0
    assert memory.slippage_risk_score > 0.5


def test_expected_only_slippage_memory_has_low_confidence():
    memory = SlippageMemoryBuilder().build([{"expected_slippage_bps": 30, "expected_fill_score": 0.8}], market_family="sports")

    assert memory.avg_expected_slippage_bps == 30
    assert memory.avg_realized_slippage_bps is None
    assert memory.confidence < 0.3
