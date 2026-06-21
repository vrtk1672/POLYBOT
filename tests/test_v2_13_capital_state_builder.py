from app.capital.capital_state_builder import CapitalStateBuilder


def test_capital_state_builder_marks_missing_data():
    state = CapitalStateBuilder().build(runtime_mode="DATA_ONLY", manual_payload={"total_capital_usd": 0})
    assert state.insufficient_data is True
    assert "missing_total_capital" in state.insufficient_data_reasons


def test_capital_state_builder_preserves_reserves():
    state = CapitalStateBuilder().build(
        runtime_mode="DATA_ONLY",
        manual_payload={"total_capital_usd": 1000, "available_capital_usd": 800, "realized_pnl_usd": 100},
    )
    assert state.survival_reserve_usd >= 200
    assert state.cash_reserve_usd >= 100
    assert state.profit_pocket_usd == 100

