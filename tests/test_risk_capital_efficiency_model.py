from __future__ import annotations

from decimal import Decimal

from app.services import capital_efficiency as ce


def test_capital_efficiency_score_formula_is_deterministic_for_current_block_shape() -> None:
    values = {
        "reward_per_dollar_hour": Decimal("0.0003561497"),
        "liquidity_exit_quality": "FAIR",
        "rules_risk": "HIGH",
        "risk_of_reversal": "HIGH",
        "time_to_resolution_seconds": 17_211_102,
    }

    score = ce._score(values, [])
    recommendation, reason = ce._recommendation(values, [], score)

    assert score == Decimal("0.2000")
    assert recommendation == "CAPITAL_BLOCK"
    assert "weak" in reason.lower()


def test_strong_reward_per_dollar_hour_can_support_without_threshold_change() -> None:
    values = {
        "reward_per_dollar_hour": Decimal("0.25"),
        "liquidity_exit_quality": "GOOD",
        "rules_risk": "LOW",
        "risk_of_reversal": "LOW",
        "time_to_resolution_seconds": 3600,
        "current_return_pct": Decimal("0"),
        "hold_return_pct": Decimal("1"),
    }

    score = ce._score(values, [])
    recommendation, _reason = ce._recommendation(values, [], score)

    assert score == Decimal("0.9000")
    assert recommendation == "CAPITAL_SUPPORT"


def test_missing_reward_evidence_is_specific_insufficient_data() -> None:
    values = {
        "reward_per_dollar_hour": None,
        "liquidity_exit_quality": "FAIR",
        "rules_risk": "LOW",
        "risk_of_reversal": "LOW",
        "time_to_resolution_seconds": 3600,
    }

    score = ce._score(values, ["POTENTIAL_REWARD_MISSING"])
    recommendation, reason = ce._recommendation(values, ["POTENTIAL_REWARD_MISSING"], score)

    assert score is None
    assert recommendation == "CAPITAL_INSUFFICIENT_DATA"
    assert "missing locked capital or potential reward" in reason.lower()
