from __future__ import annotations

import pytest

from app.neural_mesh.runtime_brain_adapter import RuntimeBrainInput, RuntimeBrainProducerRun


def test_runtime_brain_input_is_non_executing() -> None:
    item = RuntimeBrainInput(signal_id="sig-1", decision_type="WEAK_SIGNAL", paper_allowed=False, execution_allowed=False)

    assert item.paper_allowed is False
    assert item.execution_allowed is False


def test_runtime_brain_input_rejects_execution_or_paper_allowed() -> None:
    with pytest.raises(ValueError):
        RuntimeBrainInput(signal_id="sig-1", decision_type="OBSERVE", paper_allowed=True)
    with pytest.raises(ValueError):
        RuntimeBrainInput(signal_id="sig-1", decision_type="OBSERVE", execution_allowed=True)


def test_runtime_brain_run_rejects_paper_ready_execution_and_coordinator_creation() -> None:
    with pytest.raises(ValueError):
        RuntimeBrainProducerRun(run_id="run-1", paper_ready_after=True)
    with pytest.raises(ValueError):
        RuntimeBrainProducerRun(run_id="run-2", orders_created=1)
    with pytest.raises(ValueError):
        RuntimeBrainProducerRun(run_id="run-3", coordinator_runtime_decisions=1)
