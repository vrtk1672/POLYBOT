from __future__ import annotations

from app.control_center.paper_actionability import _reconcile_lifecycle_gate_actionability


def _edge():
    return {
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
    }


def _trace(**overrides):
    trace = {
        "actionability_class": "ACTIONABLE_SMALL_PAPER",
        "critical_blockers": [],
        "risk_gate_state": "RISK_REVIEW",
        "capital_gate_state": "CAPITAL_OK",
        "orderbook_gate_state": "FRESH",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "exit_gate_state": "EXIT_READY",
        "stale_gate_selected": False,
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
        "lifecycle_decision_id": "lifecycle-1",
    }
    trace.update(overrides)
    return trace


def test_lifecycle_gate_trace_can_promote_to_actionable_if_paper_enabled() -> None:
    state, operational, confidence, blockers, required, next_state = _reconcile_lifecycle_gate_actionability(
        "BLOCKED_BY_LIFECYCLE",
        "EXECUTION_DISABLED_PAPER_OFF",
        "LOW",
        ["BLOCKED_BY_LIFECYCLE", "STALE_ORDERBOOK"],
        [],
        "WAITING_FOR_LIFECYCLE_CLEARANCE",
        _trace(),
        edge=_edge(),
        paper_simulation_enabled=False,
        duplicate_active_intent_risk=False,
        open_paper_position_conflict=False,
    )

    assert state == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"
    assert operational == "EXECUTION_DISABLED_PAPER_OFF"
    assert confidence == "HIGH"
    assert blockers == ["PAPER_SIMULATION_OFF"]
    assert required
    assert next_state == "ENABLE_PAPER_SIMULATION_IN_PHASE_10_ONLY"


def test_exit_not_ready_remains_current_blocker() -> None:
    state, _operational, _confidence, blockers, _required, _next_state = _reconcile_lifecycle_gate_actionability(
        "BLOCKED_BY_LIFECYCLE",
        "EXECUTION_DISABLED_PAPER_OFF",
        "LOW",
        ["BLOCKED_BY_LIFECYCLE"],
        [],
        "WAITING_FOR_LIFECYCLE_CLEARANCE",
        _trace(exit_gate_state="INSUFFICIENT_DATA"),
        edge=_edge(),
        paper_simulation_enabled=False,
        duplicate_active_intent_risk=False,
        open_paper_position_conflict=False,
    )

    assert state == "BLOCKED_BY_EXIT"
    assert "BLOCKED_BY_EXIT_CURRENT" in blockers


def test_duplicate_guard_still_wins_over_clear_lifecycle_trace() -> None:
    state, operational, _confidence, blockers, _required, _next_state = _reconcile_lifecycle_gate_actionability(
        "WATCH_FOR_CONFIRMATION",
        "EXECUTION_DISABLED_PAPER_OFF",
        "HIGH",
        [],
        [],
        "WATCH_FOR_CONFIRMATION",
        _trace(),
        edge=_edge(),
        paper_simulation_enabled=False,
        duplicate_active_intent_risk=True,
        open_paper_position_conflict=False,
    )

    assert state == "BLOCKED_BY_DUPLICATE"
    assert operational == "EXECUTION_DISABLED_SAFETY"
    assert "BLOCKED_BY_DUPLICATE" in blockers
