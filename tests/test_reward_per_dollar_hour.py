from __future__ import annotations

from decimal import Decimal

from app.services import capital_efficiency as ce


def test_reward_per_dollar_hour_units_are_profit_per_locked_dollar_per_hour() -> None:
    values, missing = ce._metrics(
        {
            "subject_type": "PAPER_CANDIDATE",
            "subject_id": "candidate-1",
            "opened_at": None,
        },
        {"available_balance": Decimal("1000"), "open_exposure": Decimal("0")},
        {"stake_usd": Decimal("100"), "profit_if_win": Decimal("170.2702702703"), "max_loss": Decimal("100")},
        {
            "time_to_resolution_seconds": 17_211_102,
            "hold_to_resolution_profit_if_win": Decimal("170.2702702703"),
            "hold_to_resolution_max_loss": Decimal("100"),
            "liquidity_exit_quality": "FAIR",
            "rules_risk": "HIGH",
            "risk_of_reversal": "HIGH",
        },
        None,
    )

    assert missing == []
    assert values["capital_locked"] == Decimal("100")
    assert values["potential_reward"] == Decimal("170.2702702703")
    assert values["reward_per_locked_dollar"].quantize(Decimal("0.0001")) == Decimal("1.7027")
    assert values["reward_per_dollar_hour"].quantize(Decimal("0.0000001")) == Decimal("0.0003561")


def test_percent_decimal_inputs_are_not_double_divided() -> None:
    values, missing = ce._metrics(
        {"subject_type": "PAPER_CANDIDATE", "subject_id": "candidate-2"},
        {"available_balance": Decimal("1000"), "open_exposure": Decimal("0")},
        {"stake_usd": Decimal("10"), "profit_if_win": Decimal("1"), "max_loss": Decimal("10")},
        {"time_to_resolution_seconds": 3600, "hold_to_resolution_profit_if_win": Decimal("1")},
        None,
    )

    assert missing == []
    assert values["reward_per_locked_dollar"] == Decimal("0.1")
    assert values["reward_per_dollar_hour"] == Decimal("0.1")
