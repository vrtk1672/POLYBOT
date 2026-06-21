from __future__ import annotations

from app.services.lifecycle_governance import _risk_capital_summary


def test_risk_capital_current_blocker_exposes_required_to_pass() -> None:
    summary = _risk_capital_summary(
        {
            "evaluation_id": "capital-eff-1",
            "recommendation": "CAPITAL_BLOCK",
            "capital_efficiency_score": 0.2,
            "reward_per_dollar_hour": 0.0004,
            "capital_locked": 1,
            "missing_inputs": [],
        },
        {
            "risk_decision": "RISK_BLOCK",
            "blocking_evidence_json": ["RISK_BLOCKED_CAPITAL"],
        },
    )

    assert summary["risk_capital_blocker"] == "RISK_BLOCKED_CAPITAL"
    assert summary["classification"] == "CURRENT_REAL_BLOCKER"
    assert summary["risk_capital_policy_state"] == "CAPITAL_BLOCK"
    assert summary["required_to_pass"]


def test_lifecycle_capital_ok_does_not_override_risk_capital_policy() -> None:
    summary = _risk_capital_summary(
        {"recommendation": "CAPITAL_BLOCK", "missing_inputs": []},
        {"risk_decision": "RISK_BLOCK", "blocking_evidence_json": ["RISK_BLOCKED_CAPITAL"]},
    )

    assert summary["classification"] == "CURRENT_REAL_BLOCKER"
    assert summary["risk_capital_blocker"] == "RISK_BLOCKED_CAPITAL"


def test_risk_capital_watch_is_not_a_capital_block() -> None:
    summary = _risk_capital_summary(
        {"evaluation_id": "capital-eff-2", "recommendation": "CAPITAL_WATCH", "missing_inputs": []},
        {"risk_decision": "RISK_REVIEW", "blocking_evidence_json": []},
    )

    assert summary["classification"] == "PASSED"
    assert summary["risk_capital_blocker"] is None
