from __future__ import annotations

from app.control_center.decision_propagation_trace import _phase10_gate
from app.control_center.paper_actionability import _reconcile_lifecycle_gate_actionability


def _edge() -> dict[str, object]:
    return {
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
    }


def _trace(**overrides) -> dict[str, object]:
    trace = {
        "actionability_class": "ACTIONABLE_SMALL_PAPER",
        "critical_blockers": [],
        "risk_gate_state": "RISK_SUPPORT",
        "capital_gate_state": "CAPITAL_OK",
        "orderbook_gate_state": "FRESH",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "exit_gate_state": "EXIT_READY",
        "stale_gate_selected": False,
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
        "lifecycle_decision_id": "lifecycle-1",
        "risk_capital_gate_trace": {"classification": "PASSED", "risk_capital_policy_state": "CAPITAL_SUPPORT"},
        "exit_gate_trace": {"classification": "READY", "status": "EXIT_READY"},
    }
    trace.update(overrides)
    return trace


def test_all_current_gates_clear_reaches_actionable_if_paper_enabled() -> None:
    state, operational, confidence, blockers, required, next_state = _reconcile_lifecycle_gate_actionability(
        "BLOCKED_BY_RISK",
        "EXECUTION_DISABLED_PAPER_OFF",
        "LOW",
        ["BLOCKED_BY_RISK"],
        [],
        "WAITING_FOR_RISK_CLEARANCE",
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


def test_actionability_exposes_risk_capital_phase10_gate() -> None:
    action = {
        "candidate_paper_actionability_state": "BLOCKED_BY_RISK",
        "risk_gate_state": "RISK_BLOCK",
        "risk_capital_gate_trace": {"risk_capital_blocker": "RISK_BLOCKED_CAPITAL"},
    }

    assert _phase10_gate(action) == "RISK_BLOCKED_CAPITAL"


def test_actionability_exposes_exit_phase10_gate() -> None:
    action = {
        "candidate_paper_actionability_state": "BLOCKED_BY_EXIT",
        "exit_gate_trace": {"status": "EXIT_NOT_READY"},
    }

    assert _phase10_gate(action) == "EXIT_NOT_READY"
