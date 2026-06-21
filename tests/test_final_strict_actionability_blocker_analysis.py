from __future__ import annotations

from app.control_center.paper_actionability import _reconcile_strict_actionability, is_strictly_paper_actionable

from tests_support_strict_actionability import qualified_actionability_item


def test_fully_qualified_candidate_can_be_strictly_actionable() -> None:
    item = qualified_actionability_item()

    ok, state, blockers, required = is_strictly_paper_actionable(item)

    assert ok is True
    assert state is None
    assert blockers == []
    assert required == []


def test_wrong_selected_cycle_does_not_use_thesis_link() -> None:
    item = qualified_actionability_item(
        joined_trade_thesis={
            "candidate_id": "candidate-1",
            "side": "YES",
            "token_id": "token-yes",
            "source_refresh_cycle_id": "older-cycle",
            "status": "THESIS_SUPPORTED",
        }
    )

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["candidate_paper_actionability_state"] == "NOT_ACTIONABLE_MISSING_TRADE_THESIS_LINK"


def test_strict_failure_does_not_request_paper_execution() -> None:
    item = qualified_actionability_item(risk_gate_state="RISK_REVIEW")

    reconciled = _reconcile_strict_actionability(item, paper_simulation_enabled=False)

    assert reconciled["would_require_paper_simulation_on"] is False
    assert reconciled["operational_paper_execution_state"] == "EXECUTION_DISABLED_STRICT_QUALIFICATION"
