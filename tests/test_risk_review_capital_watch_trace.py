from __future__ import annotations

from app.control_center.paper_actionability import (
    _current_gate_blockers_from_trace,
    _reconcile_strict_actionability,
    _state_from_gate_trace,
)

from tests_support_strict_actionability import qualified_actionability_item


def test_risk_review_blocks_strict_actionability() -> None:
    item = qualified_actionability_item(risk_gate_state="RISK_REVIEW")

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_RISK_REVIEW"
    assert "RISK_REVIEW" in reconciled["blockers"]


def test_capital_watch_blocks_when_policy_requires_support() -> None:
    item = qualified_actionability_item(
        risk_capital_gate_trace={"classification": "PASSED", "risk_capital_policy_state": "CAPITAL_WATCH"},
        risk_capital_policy_state="CAPITAL_WATCH",
    )

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_CAPITAL_BLOCKED"
    assert "CAPITAL_NOT_STRICTLY_APPROVED" in reconciled["blockers"]


def test_lifecycle_trace_exposes_risk_review_and_capital_watch_specificity() -> None:
    trace = {
        "risk_gate_state": "RISK_REVIEW",
        "capital_gate_state": "CAPITAL_OK",
        "risk_capital_gate_trace": {"classification": "PASSED", "risk_capital_policy_state": "CAPITAL_WATCH"},
        "orderbook_gate_state": "FRESH",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "exit_gate_state": "EXIT_READY",
    }

    mapped = _state_from_gate_trace(trace)

    assert mapped == "BLOCKED_BY_RISK"
    blockers = _current_gate_blockers_from_trace(trace, mapped)
    assert "BLOCKED_BY_RISK_REVIEW" in blockers
    assert "BLOCKED_BY_CAPITAL_WATCH" in blockers
