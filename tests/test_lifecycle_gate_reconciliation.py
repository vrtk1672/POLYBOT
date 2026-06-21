from __future__ import annotations

from app.control_center.paper_actionability import _decision_cycle_consistent, _propagation_breakpoint


def test_decision_cycle_consistent_requires_matching_lifecycle_risk_context() -> None:
    edge = {
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
        "propagation_context": {"source_refresh_cycle_id": "cycle-1"},
    }
    trace = {
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
        "lifecycle_decision_id": "lifecycle-1",
    }

    assert _decision_cycle_consistent(edge, trace) is True


def test_decision_cycle_consistent_rejects_stale_lifecycle_risk_context() -> None:
    edge = {
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-fresh",
        "propagation_context": {"source_refresh_cycle_id": "cycle-1"},
    }
    trace = {
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-stale",
        "lifecycle_decision_id": "lifecycle-1",
    }

    assert _decision_cycle_consistent(edge, trace) is False


def test_propagation_breakpoint_reports_stale_lifecycle_gate_selection() -> None:
    edge = {
        "source_refresh_cycle_id": "cycle-1",
        "risk_evidence_id": "risk-1",
        "edge_state": "EDGE_SUPPORTED",
        "propagation_context": {"source_refresh_cycle_id": "cycle-1"},
    }
    trace = {"lifecycle_decision_id": "lifecycle-1", "stale_gate_selected": True}

    assert _propagation_breakpoint(edge, "BLOCKED_BY_LIFECYCLE", trace) == "LIFECYCLE_STALE_GATE_SELECTED"
