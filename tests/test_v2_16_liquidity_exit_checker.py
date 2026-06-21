from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.liquidity_exit_checker import LiquidityExitChecker
from test_v2_16_fixtures import current_market, exit_plan_manual


def test_missing_bid_ask_blocks_exit_intent():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    ok, reasons = LiquidityExitChecker().check(plan=plan, current=current_market(best_bid=0, best_ask=0))
    assert ok is False
    assert "missing_bid_ask" in reasons


def test_high_exit_slippage_blocks_or_records_failure():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    ok, reasons = LiquidityExitChecker().check(plan=plan, current=current_market(expected_slippage_bps=900))
    assert ok is False
    assert "exit_slippage_too_high" in reasons

