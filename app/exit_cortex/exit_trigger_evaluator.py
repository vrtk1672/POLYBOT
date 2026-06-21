from __future__ import annotations

from datetime import UTC, datetime

from app.exit_cortex.contracts import ExitDecision, ExitTrigger
from app.exit_cortex.emergency_exit_evaluator import EmergencyExitEvaluator
from app.exit_cortex.momentum_decay_evaluator import MomentumDecayEvaluator
from app.exit_cortex.news_invalidation_evaluator import NewsInvalidationEvaluator
from app.exit_cortex.spread_exit_evaluator import SpreadExitEvaluator


class ExitTriggerEvaluator:
    def __init__(self) -> None:
        self.emergency = EmergencyExitEvaluator()
        self.momentum = MomentumDecayEvaluator()
        self.spread = SpreadExitEvaluator()
        self.news = NewsInvalidationEvaluator()

    def evaluate(self, *, plan, current: dict) -> ExitDecision:
        price = float(current.get("current_price") or 0.0)
        triggers: list[ExitTrigger] = []
        if plan.target_exit is not None and price >= plan.target_exit:
            triggers.append(ExitTrigger(trigger_type="TAKE_PROFIT", triggered=True, severity="INFO", reason="target_exit_reached", current_price=price, threshold=plan.target_exit, confidence=0.9))
        if plan.partial_take_profit is not None and price >= plan.partial_take_profit:
            triggers.append(ExitTrigger(trigger_type="PARTIAL_TAKE_PROFIT", triggered=True, severity="INFO", reason="partial_take_profit_reached", current_price=price, threshold=plan.partial_take_profit, confidence=0.85))
        if plan.stop_loss is not None and price <= plan.stop_loss:
            triggers.append(ExitTrigger(trigger_type="STOP_LOSS", triggered=True, severity="BLOCKING", reason="stop_loss_reached", current_price=price, threshold=plan.stop_loss, confidence=0.95))
        age = float(current.get("position_age_seconds") or 0.0)
        if plan.max_hold_seconds is not None and age >= plan.max_hold_seconds:
            triggers.append(ExitTrigger(trigger_type="MAX_HOLD", triggered=True, severity="WARNING", reason="max_hold_reached", threshold=plan.max_hold_seconds, confidence=0.9, details={"position_age_seconds": age}))
        triggers.extend([self.news.evaluate(plan=plan, current=current), self.spread.evaluate(plan=plan, current=current), self.momentum.evaluate(plan=plan, current=current), self.emergency.evaluate(plan=plan, current=current)])
        active = [trigger for trigger in triggers if trigger.triggered]
        priority = ["EMERGENCY_EXIT", "STOP_LOSS", "NEWS_INVALIDATED", "MAX_HOLD", "SPREAD_EXIT", "MOMENTUM_DECAY", "TAKE_PROFIT", "PARTIAL_TAKE_PROFIT"]
        selected = None
        for item in priority:
            if any(trigger.trigger_type == item for trigger in active):
                selected = item
                break
        return ExitDecision(exit_plan_id=plan.exit_plan_id, should_exit=bool(active), triggers=triggers, selected_reason=selected, explanation="exit trigger detected" if active else "no exit trigger")

