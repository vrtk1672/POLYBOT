from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.news_invalidation_evaluator import NewsInvalidationEvaluator
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_news_invalidation_triggers():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    trigger = NewsInvalidationEvaluator().evaluate(plan=plan, current=current_market(news_invalidated=True))
    assert trigger.triggered is True

