from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.coordinator import CoordinatorDecision, CoordinatorDecisionConflict, CoordinatorDecisionInput


def test_create_valid_coordinator_decision() -> None:
    decision = CoordinatorDecision(
        market_id="market-coord",
        final_state="NO_TRADE",
        primary_reason="Risk and rules require no trade.",
        confidence=0.8,
        urgency=0.4,
        approved_actions=["MARK_NO_TRADE"],
        blocked_actions=["PAPER_ENTRY", "LIVE_ENTRY", "EXECUTION"],
        source_brain_count=2,
        input_output_count=2,
        status="ACTIVE",
    )

    assert decision.coordinator_decision_id.startswith("coord_")
    assert decision.execution_allowed is False
    assert decision.final_state == "NO_TRADE"


@pytest.mark.parametrize("final_state", ["BUY", "SELL", "PLACE_ORDER", "EXECUTE"])
def test_reject_executable_final_state(final_state: str) -> None:
    with pytest.raises(ValidationError):
        CoordinatorDecision(final_state=final_state, primary_reason="not allowed")


def test_execution_allowed_always_false() -> None:
    with pytest.raises(ValidationError):
        CoordinatorDecision(final_state="WATCH", primary_reason="watch only", execution_allowed=True)


def test_reject_executable_approved_actions() -> None:
    with pytest.raises(ValidationError):
        CoordinatorDecision(
            final_state="WATCH",
            primary_reason="watch only",
            approved_actions=["WATCH", "ORDER_CREATION"],
        )


def test_input_and_conflict_contracts_validate_ranges() -> None:
    CoordinatorDecisionInput(brain_output_id="brain_output_1", brain="risk", input_confidence=1.0)
    CoordinatorDecisionConflict(
        conflict_type="brain_output_disagreement",
        conflict_key="ai_positive_vs_risk_block",
        conflict_reason="AI cannot override risk.",
        conflict_severity=0.9,
    )

    with pytest.raises(ValidationError):
        CoordinatorDecisionInput(brain_output_id="brain_output_1", brain="risk", input_confidence=1.2)
    with pytest.raises(ValidationError):
        CoordinatorDecisionConflict(
            conflict_type="brain_output_disagreement",
            conflict_key="bad",
            conflict_reason="bad",
            conflict_severity=-0.1,
        )
