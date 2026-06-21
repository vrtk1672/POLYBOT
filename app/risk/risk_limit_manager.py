from __future__ import annotations

from app.risk.contracts import RiskLimit


class RiskLimitManager:
    def default_limits(self) -> list[RiskLimit]:
        return [
            RiskLimit(limit_type="MAX_DAILY_LOSS", value=50.0, policy={"conservative_default": True}),
            RiskLimit(limit_type="MAX_WEEKLY_LOSS", value=150.0, policy={"conservative_default": True}),
            RiskLimit(limit_type="MAX_OPEN_POSITIONS", value=5, policy={"conservative_default": True}),
            RiskLimit(limit_type="MAX_TOTAL_EXPOSURE", value=500.0, policy={"conservative_default": True}),
            RiskLimit(limit_type="MAX_TRADE_LOSS", value=25.0, policy={"conservative_default": True}),
            RiskLimit(limit_type="MAX_SLIPPAGE", value=250.0, policy={"unit": "bps", "conservative_default": True}),
            RiskLimit(limit_type="MAX_WORDING_RISK", value=0.35, policy={"conservative_default": True}),
            RiskLimit(limit_type="MIN_CONFIDENCE", value=0.55, policy={"conservative_default": True}),
            RiskLimit(limit_type="EXIT_PLAN_REQUIRED", value=True, policy={"hard_block": True}),
        ]

    def as_dict(self, limits: list[RiskLimit] | None = None) -> dict[str, float | int | bool]:
        rows = limits or self.default_limits()
        return {row.limit_type: row.value for row in rows if row.enabled}

