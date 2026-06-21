from __future__ import annotations


class AttackBankManager:
    def move_from_profit(self, *, current_available: float, profit_available: float, pct: float = 0.30) -> dict[str, float]:
        profit = max(float(profit_available or 0.0), 0.0)
        amount = round(profit * max(min(float(pct), 1.0), 0.0), 6)
        return {
            "available_usd": round(max(float(current_available or 0.0), 0.0) + amount, 6),
            "reserved_usd": 0.0,
            "used_usd": 0.0,
            "realized_profit_funded_usd": amount,
            "base_capital_used_usd": 0.0,
            "max_attack_allocation_usd": round(amount * 0.50, 6),
        }

