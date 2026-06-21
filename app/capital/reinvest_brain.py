from __future__ import annotations

from app.capital.contracts import ReinvestDecision


class ReinvestBrain:
    def evaluate(self, *, realized_profit_usd: float | None, dry_run: bool = False) -> ReinvestDecision:
        realized = max(float(realized_profit_usd or 0.0), 0.0)
        if realized <= 0:
            return ReinvestDecision(
                event_type="REINVEST_BLOCKED",
                amount_usd=0.0,
                reason="no realized profit is available for reinvestment",
                allowed=False,
                block_reason="no_realized_profit",
                dry_run=dry_run,
                policy={"base_capital_allowed": False},
            )
        return ReinvestDecision(
            event_type="PROFIT_TO_ATTACK_BANK",
            amount_usd=round(realized * 0.30, 6),
            from_bucket="PROFIT_POCKET",
            to_bucket="ATTACK_BANK",
            reason="realized profit portion may fund attack bank; base capital is untouched",
            allowed=True,
            dry_run=dry_run,
            policy={"attack_bank_pct": 0.30, "base_capital_allowed": False},
        )

