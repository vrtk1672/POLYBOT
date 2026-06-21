from __future__ import annotations

from app.exit_cortex.contracts import ExitIntent


class ExitIntentBuilder:
    def build(self, *, plan, reason: str, current: dict, trigger_snapshot: dict) -> ExitIntent:
        mode = "SHADOW_EXIT_PLAN" if plan.exit_mode == "SHADOW_EXIT_PLAN" else "PAPER_SIM_EXIT"
        size_pct = plan.partial_take_profit_pct if reason == "PARTIAL_TAKE_PROFIT" and plan.partial_take_profit_pct else 1.0
        size = plan.entry_size * size_pct
        urgency = "EMERGENCY" if reason in {"EMERGENCY_EXIT", "STOP_LOSS", "NEWS_INVALIDATED"} else "HIGH" if reason in {"MAX_HOLD", "SPREAD_EXIT"} else "NORMAL"
        status = "READY_FOR_SHADOW_PLAN" if mode == "SHADOW_EXIT_PLAN" else "READY_FOR_PAPER_EXECUTION"
        return ExitIntent(exit_plan_id=plan.exit_plan_id, order_id=plan.order_id, market_id=plan.market_id, side=plan.side, reason=reason, intent_status=status, exit_price_target=current.get("current_price") or plan.target_exit, exit_size=size, exit_size_pct=size_pct, max_slippage_bps=float((plan.liquidity_exit_check or {}).get("max_slippage_bps", 250)), urgency=urgency, execution_mode=mode, risk_snapshot=current.get("risk_snapshot") or {}, liquidity_snapshot=current.get("liquidity") or current, trigger_snapshot=trigger_snapshot)

