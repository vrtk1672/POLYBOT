from __future__ import annotations

from app.control_center.paper_actionability import _reconcile_strict_actionability


def _item_with_thesis(thesis):
    return {
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
        "thesis_id": thesis.get("thesis_id"),
        "trade_thesis_type": thesis.get("trade_thesis_type"),
        "exit_intent": thesis.get("exit_intent"),
        "expected_hold_time_hours": thesis.get("expected_hold_time_hours"),
        "hold_time_source": thesis.get("hold_time_source"),
        "joined_trade_thesis": thesis,
        "risk_capital_gate_trace": {"classification": "PASSED", "risk_capital_policy_state": "CAPITAL_SUPPORT"},
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {"actionability_class": "ACTIONABLE_SMALL_PAPER", "allow_paper_intent": True, "critical_blockers": []},
        "stale_gate_selected": False,
        "stale_sources_blocking": [],
        "blockers": ["PAPER_SIMULATION_OFF"],
    }


def test_joined_thesis_with_matching_candidate_side_token_cycle_qualifies() -> None:
    thesis = {
        "thesis_id": "thesis-1",
        "candidate_id": "candidate-1",
        "side": "YES",
        "token_id": "token-yes",
        "source_refresh_cycle_id": "cycle-1",
        "status": "THESIS_SUPPORTED",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "MISPRICING_REVERSION_WINDOW",
    }

    row = _reconcile_strict_actionability(_item_with_thesis(thesis), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "ACTIONABLE_SMALL_PAPER_IF_PAPER_ENABLED"
    assert row["strict_paper_qualification"]["qualified"] is True


def test_joined_thesis_with_wrong_cycle_is_not_actionable() -> None:
    thesis = {
        "thesis_id": "thesis-1",
        "candidate_id": "candidate-1",
        "side": "YES",
        "token_id": "token-yes",
        "source_refresh_cycle_id": "older-cycle",
        "status": "THESIS_SUPPORTED",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": 48.0,
        "hold_time_source": "MISPRICING_REVERSION_WINDOW",
    }

    row = _reconcile_strict_actionability(_item_with_thesis(thesis), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_MISSING_TRADE_THESIS_LINK"


def test_joined_thesis_without_dynamic_hold_time_is_not_actionable() -> None:
    thesis = {
        "thesis_id": "thesis-1",
        "candidate_id": "candidate-1",
        "side": "YES",
        "token_id": "token-yes",
        "source_refresh_cycle_id": "cycle-1",
        "status": "THESIS_SUPPORTED",
        "trade_thesis_type": "MISPRICING_REVERSION",
        "exit_intent": "PRICE_TARGET_EXIT",
        "expected_hold_time_hours": None,
        "hold_time_source": None,
    }

    row = _reconcile_strict_actionability(_item_with_thesis(thesis), paper_simulation_enabled=False)

    assert row["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_MISSING_DYNAMIC_HOLD_TIME"

