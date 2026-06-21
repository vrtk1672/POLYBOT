from __future__ import annotations

from app.execution_v2.fill_simulator import FillSimulator
from app.execution_v2.order_contract_builder import OrderContractBuilder
from test_v2_15_fixtures import approved_payload


def test_missing_depth_failed_fill():
    payload = approved_payload(depth=0)
    contract = OrderContractBuilder().build(market_id="m1", strategy_route=payload["strategy_route"], allocation=payload["capital_allocation"], risk_decision=payload["risk_decision"], exit_plan_id="exit_1", execution_mode="PAPER_SIM", orderbook=payload["orderbook"], liquidity=payload["liquidity"])
    fill = FillSimulator().simulate(contract)
    assert fill.fill_status == "FAILED"
    assert fill.failed_reason == "missing_depth"

