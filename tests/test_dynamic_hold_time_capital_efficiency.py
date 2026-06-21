from __future__ import annotations

from decimal import Decimal

from app.services.capital_efficiency import _metrics


def test_dynamic_reward_per_dollar_hour_uses_supported_thesis_hold_time() -> None:
    record = {"subject_type": "PAPER_CANDIDATE", "subject_id": "candidate-1", "opened_at": None}
    payout = {"stake_usd": Decimal("100"), "profit_if_win": Decimal("50")}
    exit_hold = {
        "time_to_resolution_seconds": 200 * 24 * 3600,
        "hold_to_resolution_profit_if_win": Decimal("50"),
        "liquidity_exit_quality": "FAIR",
        "rules_risk": "LOW",
        "risk_of_reversal": "LOW",
    }
    thesis = {
        "thesis_id": "thesis-1",
        "status": "THESIS_SUPPORTED",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": Decimal("48"),
        "hold_time_source": "REVERSION_WINDOW",
    }

    values, missing = _metrics(record, {"available_balance": 1000, "open_exposure": 0}, payout, exit_hold, None, thesis)

    assert "TIME_TO_RESOLUTION_MISSING" not in missing
    assert values["reward_per_dollar_hour"] == Decimal("50") / (Decimal("100") * Decimal("48"))
    assert values["_original_resolution_hold_time_hours"] == Decimal("4800")
    assert values["_dynamic_hold_time_applied"] is True


def test_watch_thesis_does_not_short_circuit_resolution_hold_time() -> None:
    record = {"subject_type": "PAPER_CANDIDATE", "subject_id": "candidate-1", "opened_at": None}
    payout = {"stake_usd": Decimal("100"), "profit_if_win": Decimal("50")}
    exit_hold = {
        "time_to_resolution_seconds": 200 * 24 * 3600,
        "hold_to_resolution_profit_if_win": Decimal("50"),
        "liquidity_exit_quality": "FAIR",
        "rules_risk": "LOW",
        "risk_of_reversal": "LOW",
    }
    thesis = {
        "thesis_id": "thesis-1",
        "status": "THESIS_WATCH",
        "trade_thesis_type": "ORDERBOOK_PRESSURE_TRADE",
        "exit_intent": "MOMENTUM_EXIT",
        "expected_hold_time_hours": Decimal("3"),
        "hold_time_source": "MOMENTUM_WINDOW",
    }

    values, _missing = _metrics(record, {"available_balance": 1000, "open_exposure": 0}, payout, exit_hold, None, thesis)

    assert values["reward_per_dollar_hour"] == Decimal("50") / (Decimal("100") * Decimal("4800"))
    assert values["_dynamic_hold_time_applied"] is False
