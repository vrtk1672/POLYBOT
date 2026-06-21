from app.brains.capital_brain import CapitalBrain
from app.brains.contracts import CapitalBrainInput


def _input(**overrides):
    base = {
        "market_id": "m1",
        "candidate_engine": "strike",
        "balance": 1000,
        "available_capital": 800,
        "locked_capital": 100,
        "open_positions": [{"notional_usd": 100}],
        "engine_budgets": {"strike": 200},
        "risk_limits": {"min_cash_reserve_pct": 0.2, "max_alloc_pct": 0.1, "max_open_exposure_pct": 0.8},
        "memory_snapshot": {"confidence": 0.8, "slippage_memory": [{"slippage_risk_score": 0.1}]},
        "data_completeness_score": 1.0,
    }
    base.update(overrides)
    return CapitalBrainInput(**base)


def test_capital_blocks_if_cash_reserve_too_low():
    output = CapitalBrain().analyze(_input(available_capital=100))

    assert output.capital_allowed is False
    assert output.block_reason == "cash_reserve_too_low"


def test_capital_blocks_if_available_capital_missing():
    output = CapitalBrain().analyze(_input(available_capital=None))

    assert output.capital_allowed is False
    assert output.insufficient_data is True
    assert "missing_available_capital" in output.insufficient_data_reasons


def test_capital_blocks_if_engine_budget_exhausted_and_respects_budget():
    output = CapitalBrain().analyze(_input(engine_budgets={"strike": 0}))

    assert output.capital_allowed is False
    assert output.block_reason == "engine_budget_exhausted"

    allowed = CapitalBrain().analyze(_input(engine_budgets={"strike": 50}))
    assert allowed.capital_allowed is True
    assert allowed.max_position_size_usd <= 50


def test_capital_blocks_open_exposure_and_reduces_size_for_slippage():
    exposure_block = CapitalBrain().analyze(_input(open_positions=[{"notional_usd": 900}]))
    assert exposure_block.capital_allowed is False
    assert exposure_block.block_reason == "open_exposure_too_high"

    high_slippage = CapitalBrain().analyze(_input(memory_snapshot={"confidence": 0.8, "slippage_memory": [{"slippage_risk_score": 0.75}]}))
    assert high_slippage.capital_allowed is False
    assert high_slippage.block_reason == "unsafe_slippage_memory"


def test_capital_recommendation_does_not_mutate_input_state():
    payload = _input()
    before = payload.available_capital
    output = CapitalBrain().analyze(payload)

    assert output.capital_allowed is True
    assert payload.available_capital == before
