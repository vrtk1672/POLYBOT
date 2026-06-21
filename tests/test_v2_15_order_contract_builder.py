from __future__ import annotations

from app.execution_v2.order_contract_builder import OrderContractBuilder
from test_v2_15_fixtures import approved_payload


def test_limit_contract_uses_orderbook_not_last_price_and_enforces_entry_max():
    payload = approved_payload()
    payload["orderbook"]["best_ask"] = 0.70
    route = payload["strategy_route"]
    contract = OrderContractBuilder().build(market_id="m1", strategy_route=route, allocation=payload["capital_allocation"], risk_decision=payload["risk_decision"], exit_plan_id="exit_placeholder", execution_mode="PAPER_SIM", orderbook=payload["orderbook"], liquidity=payload["liquidity"])

    assert contract.order_type == "LIMIT"
    assert contract.price == 0.55
    assert contract.exit_plan_id == "exit_placeholder"

