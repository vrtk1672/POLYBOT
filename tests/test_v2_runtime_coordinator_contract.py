from __future__ import annotations

import pytest

from app.neural_mesh.runtime_coordinator import RuntimeCoordinatorInput, RuntimeCoordinatorRun


def test_runtime_coordinator_input_is_non_executing() -> None:
    item = RuntimeCoordinatorInput(
        brain_output_id="brain_output_1",
        coordinator_decision_type="NO_TRADE",
        blockers=["WEAK_SIGNAL"],
    )

    assert item.paper_allowed is False
    assert item.execution_allowed is False
    assert item.order_intent_allowed is False


@pytest.mark.parametrize("field", ["paper_allowed", "execution_allowed", "order_intent_allowed"])
def test_runtime_coordinator_input_rejects_executable_flags(field: str) -> None:
    with pytest.raises(ValueError):
        RuntimeCoordinatorInput(
            brain_output_id="brain_output_1",
            coordinator_decision_type="NO_TRADE",
            **{field: True},
        )


def test_runtime_coordinator_run_rejects_safety_mutation() -> None:
    with pytest.raises(ValueError):
        RuntimeCoordinatorRun(
            run_id="run_1",
            status="OK",
            started_at="2026-01-01T00:00:00Z",
            orders_created=1,
        )


def test_runtime_coordinator_run_rejects_paper_ready() -> None:
    with pytest.raises(ValueError):
        RuntimeCoordinatorRun(
            run_id="run_1",
            status="OK",
            started_at="2026-01-01T00:00:00Z",
            paper_ready_after=True,
        )
