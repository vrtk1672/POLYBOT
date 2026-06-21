from __future__ import annotations


class ProfitPocketManager:
    def update_from_realized_profit(self, *, current_available: float, realized_profit_usd: float) -> dict[str, float]:
        realized = max(float(realized_profit_usd or 0.0), 0.0)
        available = max(float(current_available or 0.0), 0.0) + realized
        return {
            "total_realized_profit_usd": available,
            "available_profit_usd": available,
            "reserved_profit_usd": 0.0,
            "withdrawn_profit_usd": 0.0,
            "reinvested_profit_usd": 0.0,
        }

