from app.capital.capital_allocator import CapitalAllocatorV2
from app.capital.capital_state_builder import CapitalStateBuilder
from app.capital.contracts import CapitalAllocationRequest
from app.capital.engine_budget_manager import EngineBudgetManager


def test_capital_allocator_dry_run_is_not_order():
    state = CapitalStateBuilder().build(manual_payload={"total_capital_usd": 1000, "available_capital_usd": 1000})
    budgets = EngineBudgetManager().build_default_budgets(state)
    decision = CapitalAllocatorV2().allocate(
        CapitalAllocationRequest(market_id="m1", side="YES", engine="SAFE", route_status="ROUTED", requested_size_usd=50, dry_run=True),
        state,
        budgets,
    )
    assert decision.allocation_status == "DRY_RUN"
    assert decision.constraints["not_executable_order"] is True

