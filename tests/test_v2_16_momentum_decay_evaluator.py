from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.momentum_decay_evaluator import MomentumDecayEvaluator
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_momentum_decay_triggers():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    trigger = MomentumDecayEvaluator().evaluate(plan=plan, current=current_market(momentum_score=0.1))
    assert trigger.triggered is True

