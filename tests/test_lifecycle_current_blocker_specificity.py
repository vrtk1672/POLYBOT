from __future__ import annotations

from app.control_center.paper_actionability import (
    _current_gate_blockers_from_trace,
    _lifecycle_gate_ready,
    _reconcile_strict_actionability,
    _state_from_gate_trace,
)


def _trace(**overrides):
    trace = {
        "actionability_class": "WATCH_FOR_CONFIRMATION",
        "allow_paper_intent": False,
        "critical_blockers": [],
        "risk_gate_state": "RISK_REVIEW",
        "capital_gate_state": "CAPITAL_OK",
        "risk_capital_gate_trace": {
            "classification": "PASSED",
            "risk_capital_policy_state": "CAPITAL_WATCH",
        },
        "orderbook_gate_state": "FRESH",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "exit_gate_state": "EXIT_READY",
        "stale_gate_selected": False,
    }
    trace.update(overrides)
    return trace


def _qualified_item(**overrides):
    item = {
        "candidate_id": "candidate-1",
        "market_id": "market-1",
        "side": "YES",
        "token_id": "token-yes",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "operational_paper_execution_state": "EXECUTION_DISABLED_PAPER_OFF",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "risk_gate_state": "RISK_SUPPORT",
        "capital_gate_state": "CAPITAL_OK",
        "exit_gate_state": "EXIT_READY",
        "exit_readiness_state": "EXIT_READY",
        "source_refresh_cycle_id": "cycle-1",
        "thesis_id": "thesis-1",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "REVERSION_WINDOW",
        "joined_trade_thesis": {
            "candidate_id": "candidate-1",
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "cycle-1",
            "status": "THESIS_SUPPORTED",
        },
        "risk_capital_gate_trace": {
            "classification": "PASSED",
            "risk_capital_policy_state": "CAPITAL_SUPPORT",
        },
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {
            "actionability_class": "ACTIONABLE_SMALL_PAPER",
            "allow_paper_intent": True,
            "critical_blockers": [],
        },
        "blockers": [],
    }
    item.update(overrides)
    return item


def test_lifecycle_trace_risk_review_maps_to_specific_risk_blocker() -> None:
    trace = _trace(risk_gate_state="RISK_REVIEW")

    assert _state_from_gate_trace(trace) == "BLOCKED_BY_RISK"
    assert "BLOCKED_BY_RISK_REVIEW" in _current_gate_blockers_from_trace(trace, "BLOCKED_BY_RISK")
    assert _lifecycle_gate_ready(trace, edge={}) is False


def test_lifecycle_trace_capital_watch_maps_to_specific_capital_blocker() -> None:
    trace = _trace(risk_gate_state="RISK_SUPPORT")

    assert _state_from_gate_trace(trace) == "BLOCKED_BY_CAPITAL"
    assert "BLOCKED_BY_CAPITAL_WATCH" in _current_gate_blockers_from_trace(trace, "BLOCKED_BY_CAPITAL")
    assert _lifecycle_gate_ready(trace, edge={}) is False


def test_generic_lifecycle_state_is_demoted_to_strict_event_scope_blocker() -> None:
    item = _qualified_item(
        candidate_paper_actionability_state="BLOCKED_BY_LIFECYCLE",
        paper_actionability_state="BLOCKED_BY_LIFECYCLE",
        candidate_event_scope="NOT_ACTIONABLE",
        candidate_event_actionability_scope="NOT_ACTIONABLE",
        candidate_event_link_state="STALE_CANDIDATE_LINK",
        blockers=["MISSING_CANDIDATE_EVENT_LINK", "BLOCKED_BY_LIFECYCLE_CURRENT"],
    )

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_EVENT_SCOPE"
    assert reconciled["strict_paper_qualification"]["qualified"] is False
    assert "NOT_ACTIONABLE_EVENT_SCOPE" in reconciled["strict_paper_qualification"]["blockers"]
