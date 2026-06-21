from __future__ import annotations

from app.services.lifecycle_governance import _risk_capital_summary


def test_capital_ok_and_risk_capital_block_are_distinct_concepts() -> None:
    summary = _risk_capital_summary(
        {
            "recommendation": "CAPITAL_BLOCK",
            "capital_efficiency_score": 0.2,
            "reward_per_dollar_hour": 0.000356,
            "capital_locked": 100,
            "missing_inputs_json": [],
            "evaluation_id": "capital-efficiency-test",
        },
        {"risk_decision": "RISK_BLOCK"},
    )

    assert summary["classification"] == "CURRENT_REAL_BLOCKER"
    assert summary["capital_gate_state"] == "CAPITAL_BLOCK"
    assert summary["risk_capital_blocker"] == "RISK_BLOCKED_CAPITAL"
    assert summary["required_to_pass"]


def test_capital_support_passes_risk_capital_trace() -> None:
    summary = _risk_capital_summary(
        {
            "recommendation": "CAPITAL_SUPPORT",
            "capital_efficiency_score": 0.9,
            "reward_per_dollar_hour": 0.25,
            "capital_locked": 10,
            "missing_inputs_json": [],
            "evaluation_id": "capital-efficiency-support",
        },
        {"risk_decision": "RISK_OK"},
    )

    assert summary["classification"] == "PASSED"
    assert summary["risk_capital_blocker"] is None
    assert summary["required_to_pass"] == []


def test_missing_reward_evidence_trace_is_specific() -> None:
    summary = _risk_capital_summary(
        {
            "recommendation": "CAPITAL_INSUFFICIENT_DATA",
            "missing_inputs_json": ["POTENTIAL_REWARD_MISSING"],
            "evaluation_id": "capital-efficiency-missing",
        },
        {"risk_decision": "RISK_BLOCK"},
    )

    assert summary["classification"] == "POLICY_MISMATCH"
    assert "POTENTIAL_REWARD_MISSING" in summary["missing_inputs"]
    assert summary["required_to_pass"]
