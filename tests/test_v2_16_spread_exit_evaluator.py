from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.spread_exit_evaluator import SpreadExitEvaluator
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_spread_exit_triggers():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    trigger = SpreadExitEvaluator().evaluate(plan=plan, current=current_market(spread_bps=999))
    assert trigger.triggered is True

