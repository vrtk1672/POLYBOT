from app.market_memory.no_trade_memory_builder import NoTradeMemoryBuilder


def test_no_trade_memory_records_regret_only_with_post_fact_evidence():
    memory = NoTradeMemoryBuilder().build(
        [
            {"regret": True, "would_have_roi": 0.1, "reason": "wide_spread"},
            {"regret": False, "would_have_roi": -0.05, "reason": "wide_spread"},
        ],
        market_family="crypto",
        candidate_engine="strike",
        reason="wide_spread",
    )

    assert memory.observations_count == 2
    assert memory.regret_rate == 0.5
    assert memory.avg_would_have_roi == 0.025
    assert 0 <= memory.no_trade_quality_score <= 1
    assert memory.confidence > 0


def test_no_trade_memory_without_records_is_insufficient_data():
    memory = NoTradeMemoryBuilder().build([], market_family="sports", reason="insufficient_data")

    assert memory.observations_count == 0
    assert memory.regret_rate == 0
    assert memory.confidence == 0
    assert memory.summary["insufficient_data"] is True
