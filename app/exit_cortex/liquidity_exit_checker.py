from __future__ import annotations

from typing import Any


class LiquidityExitChecker:
    def check(self, *, plan: Any, current: dict[str, Any]) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        best_bid = float(current.get("best_bid") or 0.0)
        best_ask = float(current.get("best_ask") or 0.0)
        depth = float(current.get("depth_2c") or current.get("depth_5c") or 0.0)
        slippage = float(current.get("expected_slippage_bps") or current.get("spread_bps") or 0.0)
        exit_quality = float(current.get("exit_quality_score") or current.get("exit_liquidity_score") or 0.0)
        limits = plan.liquidity_exit_check if hasattr(plan, "liquidity_exit_check") else {}
        if limits.get("require_bid_ask", True) and (best_bid <= 0 or best_ask <= 0):
            reasons.append("missing_bid_ask")
        if limits.get("require_depth", True) and depth <= 0:
            reasons.append("missing_exit_depth")
        if slippage > float(limits.get("max_slippage_bps", 250)):
            reasons.append("exit_slippage_too_high")
        if exit_quality and exit_quality < float(limits.get("min_exit_quality", 0.25)):
            reasons.append("exit_quality_too_low")
        return not reasons, reasons

