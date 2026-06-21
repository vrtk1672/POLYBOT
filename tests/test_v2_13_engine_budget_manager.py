from app.capital.capital_state_builder import CapitalStateBuilder
from app.capital.engine_budget_manager import EngineBudgetManager


def test_engine_budget_manager_respects_engine_buckets():
    state = CapitalStateBuilder().build(manual_payload={"total_capital_usd": 1000, "available_capital_usd": 1000})
    budgets = EngineBudgetManager().build_default_budgets(state)
    by_engine = {budget.engine: budget for budget in budgets}
    assert by_engine["SAFE"].bucket == "SAFE_CAPITAL"
    assert by_engine["HUNT"].max_position_usd < state.available_capital_usd
    assert by_engine["NO_TRADE"].enabled is False

