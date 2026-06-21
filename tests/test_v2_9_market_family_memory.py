from app.market_memory.contracts import MarketMemory
from app.market_memory.market_family_memory_builder import MarketFamilyMemoryBuilder


def test_market_family_memory_groups_markets_by_family():
    family = MarketFamilyMemoryBuilder().build(
        "sports",
        [
            MarketMemory(market_id="a", market_family="sports", avg_spread_bps=100, avg_depth_2c=500, avg_slippage_bps=20, technical_block_rate=0.0, memory_confidence=0.4, observations_count=2),
            MarketMemory(market_id="b", market_family="sports", avg_spread_bps=300, avg_depth_2c=100, avg_slippage_bps=60, technical_block_rate=0.5, memory_confidence=0.2, observations_count=1),
        ],
    )

    assert family.market_family == "sports"
    assert family.markets_count == 2
    assert family.observations_count == 3
    assert family.avg_spread_bps == 200
    assert family.avg_depth_2c == 300
    assert family.technical_block_rate == 0.25
    assert 0 < family.memory_confidence <= 1
