from app.exit_cortex.exit_intent_builder import ExitIntentBuilder
from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_exit_intent_is_paper_shadow_only():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    intent = ExitIntentBuilder().build(plan=plan, reason="TAKE_PROFIT", current=current_market(current_price=0.72), trigger_snapshot={})
    assert intent.paper_shadow_only is True
    assert intent.execution_mode == "PAPER_SIM_EXIT"
    assert intent.intent_status == "READY_FOR_PAPER_EXECUTION"


def test_partial_exit_uses_configured_pct():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    intent = ExitIntentBuilder().build(plan=plan, reason="PARTIAL_TAKE_PROFIT", current=current_market(current_price=0.65), trigger_snapshot={})
    assert intent.exit_size == 5.0
    assert intent.exit_size_pct == 0.5

