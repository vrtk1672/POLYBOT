from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.exit_trigger_evaluator import ExitTriggerEvaluator
from test_v2_16_fixtures import current_market, exit_plan_manual


def _plan(**overrides):
    return ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual(**overrides))


def _types(decision):
    return {trigger.trigger_type for trigger in decision.triggers if trigger.triggered}


def test_take_profit_and_partial_take_profit_trigger():
    decision = ExitTriggerEvaluator().evaluate(plan=_plan(), current=current_market(current_price=0.73))
    assert "TAKE_PROFIT" in _types(decision)
    assert "PARTIAL_TAKE_PROFIT" in _types(decision)


def test_stop_loss_and_max_hold_trigger():
    decision = ExitTriggerEvaluator().evaluate(plan=_plan(), current=current_market(current_price=0.37, position_age_seconds=999))
    assert "STOP_LOSS" in _types(decision)
    assert "MAX_HOLD" in _types(decision)
    assert decision.selected_reason == "STOP_LOSS"

