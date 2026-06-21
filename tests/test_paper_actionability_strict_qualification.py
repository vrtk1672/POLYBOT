from __future__ import annotations

from app.control_center.paper_actionability import _reconcile_strict_actionability, is_strictly_paper_actionable


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
            "trade_thesis_type": "MISPRICING_REVERSION",
            "exit_intent": "PRICE_TARGET_EXIT",
            "expected_hold_time_hours": 48.0,
        },
        "risk_capital_gate_trace": {
            "classification": "PASSED",
            "risk_capital_policy_state": "CAPITAL_SUPPORT",
            "capital_efficiency_score": 0.7,
        },
        "risk_capital_policy_state": "CAPITAL_SUPPORT",
        "lifecycle_gate_trace": {
            "actionability_class": "ACTIONABLE_SMALL_PAPER",
            "allow_paper_intent": True,
            "critical_blockers": [],
        },
        "stale_gate_selected": False,
        "stale_sources_blocking": [],
        "blockers": ["PAPER_SIMULATION_OFF"],
        "required_to_pass": [],
    }
    item.update(overrides)
    return item


def _strict_state(**overrides):
    item = _reconcile_strict_actionability(_qualified_item(**overrides), paper_simulation_enabled=False)
    return item["candidate_paper_actionability_state"], item


def test_not_actionable_event_scope_cannot_be_actionable() -> None:
    state, item = _strict_state(candidate_event_scope="NOT_ACTIONABLE", candidate_event_actionability_scope="NOT_ACTIONABLE")

    assert state == "NOT_ACTIONABLE_EVENT_SCOPE"
    assert item["would_require_paper_simulation_on"] is False


def test_token_side_mismatch_cannot_be_actionable() -> None:
    state, item = _strict_state(candidate_event_link_state="TOKEN_SIDE_MISMATCH")

    assert state == "NOT_ACTIONABLE_TOKEN_SIDE_MISMATCH"
    assert "TOKEN_SIDE_MISMATCH" in item["blockers"]


def test_risk_review_cannot_be_actionable() -> None:
    state, _item = _strict_state(risk_gate_state="RISK_REVIEW")

    assert state == "NOT_ACTIONABLE_RISK_REVIEW"


def test_risk_blocked_cannot_be_actionable() -> None:
    state, _item = _strict_state(risk_gate_state="RISK_BLOCKED")

    assert state == "NOT_ACTIONABLE_RISK_BLOCKED"


def test_missing_thesis_id_cannot_be_actionable() -> None:
    state, _item = _strict_state(thesis_id=None, joined_trade_thesis={})

    assert state == "NOT_ACTIONABLE_MISSING_TRADE_THESIS"


def test_missing_exit_intent_cannot_be_actionable() -> None:
    state, _item = _strict_state(exit_intent=None)

    assert state == "NOT_ACTIONABLE_MISSING_EXIT_INTENT"


def test_missing_expected_hold_time_cannot_be_actionable() -> None:
    state, _item = _strict_state(expected_hold_time_hours=None)

    assert state == "NOT_ACTIONABLE_MISSING_DYNAMIC_HOLD_TIME"


def test_fully_qualified_row_remains_actionable_if_paper_enabled() -> None:
    ok, state, blockers, required = is_strictly_paper_actionable(_qualified_item())

    assert ok is True
    assert state is None
    assert blockers == []
    assert required == []

