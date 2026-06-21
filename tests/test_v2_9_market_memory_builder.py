from app.market_memory.market_memory_builder import MarketMemoryBuilder


def test_market_memory_builder_aggregates_v2_8_technical_truth():
    memory = MarketMemoryBuilder().build(
        "m1",
        [
            {
                "price_yes": 0.55,
                "spread_bps": 200,
                "depth_1c": 100,
                "depth_2c": 250,
                "depth_5c": 500,
                "expected_fill_score": 0.8,
                "expected_slippage_bps": 35,
                "exit_quality_score": 0.7,
                "time_efficiency_score": 0.6,
                "technical_blocked": False,
                "stale": False,
            },
            {
                "price_yes": 0.65,
                "spread_bps": 400,
                "depth_1c": 50,
                "depth_2c": 150,
                "depth_5c": 300,
                "expected_fill_score": 0.6,
                "expected_slippage_bps": 65,
                "exit_quality_score": 0.5,
                "time_efficiency_score": 0.4,
                "technical_blocked": True,
                "liquidity_block_reason": "low_depth",
                "stale": True,
            },
        ],
        market_family="crypto",
        rules_rows=[{"wording_risk": 0.4, "dispute_risk": 0.2}],
    )

    assert memory.market_id == "m1"
    assert memory.market_family == "crypto"
    assert memory.avg_spread_bps == 300
    assert memory.avg_depth_2c == 200
    assert memory.avg_slippage_bps == 50
    assert memory.technical_block_rate == 0.5
    assert memory.liquidity_failure_rate == 0.5
    assert memory.stale_data_rate == 0.5
    assert 0 < memory.memory_confidence <= 1


def test_market_memory_builder_marks_insufficient_data_without_signals():
    memory = MarketMemoryBuilder().build("missing", [], market_family="sports")

    assert memory.observations_count == 0
    assert memory.best_engine == "UNKNOWN"
    assert memory.memory_status == "insufficient_data"
    assert memory.memory_confidence == 0
