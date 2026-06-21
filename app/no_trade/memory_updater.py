from __future__ import annotations

from app.no_trade.contracts import NoTradeRegretScore


class NoTradeMemoryUpdater:
    def should_update(self, regret: NoTradeRegretScore) -> bool:
        return bool(regret.update_memory and regret.confidence >= 0.6 and regret.regret_band != "INSUFFICIENT_DATA")
