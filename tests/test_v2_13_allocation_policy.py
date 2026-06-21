from app.capital.allocation_policy import AllocationPolicy
from app.capital.capital_state_builder import CapitalStateBuilder
from app.capital.contracts import CapitalAllocationRequest
from app.capital.engine_budget_manager import EngineBudgetManager


def _state(losses=0):
    return CapitalStateBuilder().build(
        manual_payload={"total_capital_usd": 1000, "available_capital_usd": 1000, "loss_streak_count": losses}
    )


def test_reserve_and_engine_budget_never_violated():
    state = _state()
    budgets = EngineBudgetManager().build_default_budgets(state)
    decision = AllocationPolicy().decide(
        CapitalAllocationRequest(market_id="m1", side="YES", engine="SAFE", route_status="ROUTED", requested_size_usd=900, max_loss_usd=100),
        state,
        budgets,
    )
    assert decision.approved_size_usd <= decision.engine_budget_before_usd
    assert decision.reserve_after_usd >= state.survival_reserve_usd + state.cash_reserve_usd
    assert decision.allocation_status == "REDUCED"


def test_no_trade_and_blocked_routes_get_no_allocation():
    state = _state()
    budgets = EngineBudgetManager().build_default_budgets(state)
    decision = AllocationPolicy().decide(
        CapitalAllocationRequest(market_id="m1", side="YES", engine="NO_TRADE", route_status="NO_TRADE", requested_size_usd=50),
        state,
        budgets,
    )
    assert decision.allocation_status == "BLOCKED"
    assert decision.approved_size_usd == 0

