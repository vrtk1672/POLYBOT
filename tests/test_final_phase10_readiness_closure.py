from __future__ import annotations

from app.services.lifecycle_governance import LifecycleGovernanceGateService


def test_phase10_closure_keeps_exit_insufficient_data_as_critical(monkeypatch) -> None:
    service = LifecycleGovernanceGateService(connection_factory=None)

    monkeypatch.setattr("app.services.lifecycle_governance._tables_ready", lambda conn: True)
    monkeypatch.setattr("app.services.lifecycle_governance._same_market_truth", lambda truth, conn, plan, guard: {"decision_permission": "CAN_AUTHORIZE"})
    monkeypatch.setattr("app.services.lifecycle_governance._legacy_risk_truth", lambda conn, plan, risk_summary, truth: {"truth_state": "ACTIVE_FRESH", "age_seconds": 1})
    monkeypatch.setattr("app.services.lifecycle_governance._event_native_capital_truth", lambda conn, plan: {"fresh": True, "capital_opinion_state": "CAPITAL_OK", "blockers": []})
    monkeypatch.setattr("app.services.lifecycle_governance._count_contributions", lambda conn, plan_id: 0)
    monkeypatch.setattr(service._freshness, "evaluate_plan_with_conn", lambda *args, **kwargs: {"critical_blockers": []})
    monkeypatch.setattr(service._risk_evidence, "latest_for_plan", lambda conn, plan: None)

    plan = {
        "plan_id": "plan-1",
        "subject_type": "PAPER_CANDIDATE",
        "subject_id": "candidate-1",
        "market_id": "market-1",
        "side": "YES",
        "token_id": "token-1",
        "strategy_type": "WATCH_ONLY",
        "plan_status": "PARTIAL",
        "decision_class": "WATCH",
        "missing_inputs_json": [],
        "risk_summary_json": {"risk_status": "LOW"},
        "exit_hold_summary_json": {"decision": "INSUFFICIENT_DATA"},
        "capital_efficiency_summary_json": {"recommendation": "CAPITAL_WATCH"},
        "capital_plan_json": {"capital_brain_decision": "CAPITAL_SUPPORT"},
        "same_market_summary_json": {"decision": "ALLOW"},
        "coordinator_judgment_json": {},
    }

    decision = service._classify_plan(None, plan, request_action="PAPER_INTENT", metadata={})

    assert decision["actionability_class"] == "HARD_BLOCK"
    assert "EXIT_BLOCKED" in decision["critical_blockers_json"]
    assert "EXIT_NOT_READY" in decision["critical_blockers_json"]


def test_phase10_readiness_requires_exit_ready_for_actionability() -> None:
    from app.control_center.paper_actionability import _lifecycle_gate_ready

    trace = {
        "actionability_class": "ACTIONABLE_SMALL_PAPER",
        "critical_blockers": [],
        "risk_gate_state": "RISK_REVIEW",
        "capital_gate_state": "CAPITAL_OK",
        "orderbook_gate_state": "FRESH",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "exit_gate_state": "INSUFFICIENT_DATA",
        "stale_gate_selected": False,
    }
    edge = {"edge_state": "EDGE_SUPPORTED", "source_backed": True, "risk_usable": True}

    assert _lifecycle_gate_ready(trace, edge) is False
