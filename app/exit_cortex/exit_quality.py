from __future__ import annotations

from app.exit_cortex.contracts import ExitQualityResult, bounded


class ExitQualityScorer:
    def score(self, *, plan, intent=None, current: dict | None = None) -> ExitQualityResult:
        current = current or {}
        expected = float(current.get("current_price") or intent.exit_price_target if intent else plan.target_exit or plan.entry_price)
        slippage = float(current.get("expected_slippage_bps") or current.get("spread_bps") or 0.0)
        liquidity = float(current.get("exit_quality_score") or current.get("exit_liquidity_score") or 0.5)
        score = bounded((liquidity * 0.65) + max(0.0, 1.0 - slippage / 1000.0) * 0.35)
        flags = []
        if slippage > float((plan.liquidity_exit_check or {}).get("max_slippage_bps", 250)):
            flags.append("high_exit_slippage")
        if liquidity < float((plan.liquidity_exit_check or {}).get("min_exit_quality", 0.25)):
            flags.append("low_exit_liquidity")
        return ExitQualityResult(exit_plan_id=plan.exit_plan_id, exit_intent_id=getattr(intent, "exit_intent_id", None), order_id=plan.order_id, market_id=plan.market_id, expected_exit_price=expected, expected_slippage_bps=slippage, expected_exit_liquidity_score=liquidity, exit_quality_score=round(score, 4), quality_flags=flags)

