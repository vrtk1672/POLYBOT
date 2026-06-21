from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from test_v2_16_fixtures import exit_plan_manual


def test_exit_plan_requires_target_stop_max_hold_and_liquidity():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual(target_exit=None, stop_loss=None, max_hold_seconds=None, liquidity_exit_check={}))
    assert plan.insufficient_data is True
    assert "missing_target_exit" in plan.insufficient_data_reasons
    assert "missing_stop_loss" in plan.insufficient_data_reasons
    assert "missing_max_hold_seconds" in plan.insufficient_data_reasons
    assert "missing_liquidity_exit_check" in plan.insufficient_data_reasons


def test_complete_exit_plan_is_active_and_explainable():
    plan = ExitPlanBuilder().build(market_id="m1", manual=exit_plan_manual())
    assert plan.plan_status == "ACTIVE"
    assert plan.target_exit == 0.72
    assert plan.stop_loss == 0.38
    assert plan.max_hold_seconds == 300
    assert plan.liquidity_exit_check["require_bid_ask"] is True

