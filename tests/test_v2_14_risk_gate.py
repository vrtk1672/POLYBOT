from app.risk.contracts import RiskGateInput, RiskGovernorState
from app.risk.risk_gate import RiskGate


def _route():
    return {
        "id": 1,
        "market_id": "m1",
        "side": "YES",
        "selected_engine": "SAFE",
        "route_status": "ROUTED",
        "route_confidence": 0.8,
        "target_exit": 0.8,
        "stop_loss": 0.3,
        "engine_contract_json": {"target_exit": 0.8, "stop_loss": 0.3},
    }


def _allocation(status="ALLOCATED"):
    return {"allocation_id": "a1", "allocation_status": status, "approved_size_usd": 25, "max_loss_usd": 10, "engine_budget_after_usd": 100}


def test_trade_without_exit_plan_blocked():
    route = _route()
    route.pop("target_exit")
    route.pop("stop_loss")
    route["engine_contract_json"] = {}
    decision = RiskGate().evaluate(RiskGateInput(market_id="m1", engine="SAFE", strategy_route=route, capital_allocation=_allocation(), governor_state=RiskGovernorState(governor_status="OK")))
    assert decision.decision == "BLOCKED"
    assert "missing_exit_plan" in decision.block_reasons


def test_strategy_no_trade_and_capital_blocked_are_blocked():
    route = _route()
    route["selected_engine"] = "NO_TRADE"
    route["route_status"] = "NO_TRADE"
    decision = RiskGate().evaluate(RiskGateInput(market_id="m1", engine="NO_TRADE", strategy_route=route, capital_allocation=_allocation("BLOCKED"), governor_state=RiskGovernorState(governor_status="OK")))
    assert decision.blocked is True
    assert "strategy_route_not_risk_eligible" in decision.block_reasons
    assert "capital_allocation_not_risk_eligible" in decision.block_reasons


def test_gate_approval_is_not_order():
    decision = RiskGate().evaluate(RiskGateInput(market_id="m1", engine="SAFE", strategy_route=_route(), capital_allocation=_allocation(), governor_state=RiskGovernorState(governor_status="OK"), data_completeness_score=1))
    assert decision.approved is True
    assert decision.constraints["not_executable_order"] is True

