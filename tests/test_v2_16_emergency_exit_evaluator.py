from app.exit_cortex.emergency_exit_evaluator import EmergencyExitEvaluator
from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_emergency_exit_triggers_on_governor_kill():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    trigger = EmergencyExitEvaluator().evaluate(plan=plan, current=current_market(governor_status="KILL"))
    assert trigger.triggered is True
    assert trigger.trigger_type == "EMERGENCY_EXIT"

