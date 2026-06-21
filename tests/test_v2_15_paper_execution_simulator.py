from __future__ import annotations

from app.execution_v2.order_contract_builder import OrderContractBuilder
from app.execution_v2.paper_execution_simulator import PaperExecutionSimulator
from test_v2_15_fixtures import approved_payload


def _contract(payload):
    return OrderContractBuilder().build(market_id="m1", strategy_route=payload["strategy_route"], allocation=payload["capital_allocation"], risk_decision=payload["risk_decision"], exit_plan_id="exit_1", execution_mode="PAPER_SIM", orderbook=payload["orderbook"], liquidity=payload["liquidity"], fee=payload["fee"])


def test_paper_execution_matches_orderbook_assumptions():
    result, quality = PaperExecutionSimulator().simulate(_contract(approved_payload(depth=1000)))
    assert result.order_status == "FILLED"
    assert result.filled_size > 0
    assert quality.execution_quality_score > 0


def test_low_depth_creates_partial_fill():
    result, _ = PaperExecutionSimulator().simulate(_contract(approved_payload(depth=35)))
    assert result.order_status == "PARTIALLY_FILLED"
    assert result.remaining_size > 0

