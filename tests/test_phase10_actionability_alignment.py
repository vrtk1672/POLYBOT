from __future__ import annotations

from app.control_center.decision_propagation_trace import _phase10_gate
from app.control_center.paper_actionability import _reconcile_strict_actionability


def _item(**overrides):
    row = {
        "candidate_id": "candidate-1",
        "market_id": "market-1",
        "side": "YES",
        "token_id": "token-yes",
        "candidate_event_scope": "CANDIDATE_SCOPED",
        "candidate_event_actionability_scope": "CANDIDATE_SCOPED",
        "candidate_event_link_state": "LINKED_TO_CANDIDATE",
        "candidate_paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "paper_actionability_state": "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED",
        "edge_state": "EDGE_SUPPORTED",
        "source_backed": True,
        "risk_usable": True,
        "risk_gate_state": "RISK_SUPPORT",
        "capital_gate_state": "CAPITAL_OK",
        "exit_gate_state": "EXIT_READY",
        "exit_readiness_state": "EXIT_READY",
        "same_market_gate_state": "CAN_AUTHORIZE",
        "source_refresh_cycle_id": "cycle-1",
        "thesis_id": "thesis-1",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "MISPRICING_REVERSION_WINDOW",
        "joined_trade_thesis": {
            "thesis_id": "thesis-1",
            "candidate_id": "candidate-1",
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "cycle-1",
            "status": "THESIS_SUPPORTED",
        },
        "risk_capital_gate_trace": {"classification": "PASSED", "risk_capital_policy_state": "CAPITAL_SUPPORT"},
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {"actionability_class": "ACTIONABLE_SMALL_PAPER", "allow_paper_intent": True, "critical_blockers": []},
        "stale_gate_selected": False,
        "stale_sources_blocking": [],
        "blockers": ["PAPER_SIMULATION_OFF"],
    }
    row.update(overrides)
    return row


def test_phase10_gate_reports_strict_not_actionable_state() -> None:
    row = _reconcile_strict_actionability(_item(risk_gate_state="RISK_REVIEW"), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_RISK_REVIEW"
    assert _phase10_gate(row) == "NOT_ACTIONABLE_RISK_REVIEW"


def test_phase10_gate_agrees_when_row_is_strictly_actionable() -> None:
    row = _reconcile_strict_actionability(_item(), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"
    assert _phase10_gate(row) == "PAPER_SIMULATION_OFF_EXPECTED"


def test_phase10_gate_rejects_token_side_mismatch() -> None:
    row = _reconcile_strict_actionability(_item(candidate_event_link_state="TOKEN_SIDE_MISMATCH"), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH"
    assert _phase10_gate(row) == "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH"

