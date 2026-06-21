from app.exit_cortex.exit_failure_handler import ExitFailureHandler
from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from test_v2_16_fixtures import exit_plan_manual


def test_exit_failure_records_bad_liquidity_instead_of_fake_success():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    failure = ExitFailureHandler().failure(plan=plan, failure_type="LIQUIDITY_EXIT_FAILED", reason="missing_bid_ask")
    assert failure.failure_type == "LIQUIDITY_EXIT_FAILED"
    assert failure.recoverable is True

