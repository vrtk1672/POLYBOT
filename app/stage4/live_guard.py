"""
Hard safety gates for Stage 4 live execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.stage4.config import Stage4Settings


@dataclass(slots=True)
class LiveGuardDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


class LiveGuard:
    def __init__(self, settings: Stage4Settings) -> None:
        self.settings = settings

    def evaluate_order(
        self,
        *,
        market_id: str,
        notional_usd: float,
        live: bool,
        armed: bool,
    ) -> LiveGuardDecision:
        reasons: list[str] = []

        if self.settings.live_kill_switch:
            reasons.append("LIVE_KILL_SWITCH is enabled")
        if not market_id:
            reasons.append("market_id is missing")
        if notional_usd <= 0:
            reasons.append("order notional must be positive")
        if notional_usd > self.settings.live_max_order_usd:
            reasons.append(
                f"order notional ${notional_usd:.2f} exceeds LIVE_MAX_ORDER_USD ${self.settings.live_max_order_usd:.2f}"
            )
        if (
            self.settings.live_optional_whitelist_mode == "subset"
            and self.settings.live_market_whitelist
            and market_id not in self.settings.live_market_whitelist
        ):
            reasons.append(f"market {market_id} is not in LIVE_MARKET_WHITELIST")

        if live:
            if not armed:
                reasons.append("--armed is required for live submission")
            if not self.settings.live_trading_enabled:
                reasons.append("LIVE_TRADING_ENABLED is false")
        return LiveGuardDecision(allowed=not reasons, reasons=reasons)
