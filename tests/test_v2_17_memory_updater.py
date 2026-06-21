from app.no_trade.contracts import NoTradeRegretScore
from app.no_trade.memory_updater import NoTradeMemoryUpdater


def test_memory_updater_skips_low_confidence_regret():
    regret = NoTradeRegretScore(no_trade_id="n1", market_id="m1", regret_band="HIGH_REGRET", confidence=0.2, update_memory=True)
    assert NoTradeMemoryUpdater().should_update(regret) is False

