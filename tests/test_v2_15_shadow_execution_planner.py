from __future__ import annotations

from app.execution_v2.order_contract_builder import OrderContractBuilder
from app.execution_v2.shadow_execution_planner import ShadowExecutionPlanner
from test_v2_15_fixtures import approved_payload


def test_shadow_plan_sends_nothing():
    payload = approved_payload(runtime_mode="SHADOW_LIVE")
    contract = OrderContractBuilder().build(market_id="m1", strategy_route=payload["strategy_route"], allocation=payload["capital_allocation"], risk_decision=payload["risk_decision"], exit_plan_id="exit_1", execution_mode="SHADOW_PLAN", orderbook=payload["orderbook"])
    plan = ShadowExecutionPlanner().plan(contract)
    assert plan.not_sent_reason == "shadow_plan_only_no_external_send"
    assert plan.expected_fill_probability > 0

