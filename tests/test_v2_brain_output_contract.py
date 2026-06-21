from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputConflict, BrainOutputDependency


def test_create_valid_brain_output_contract() -> None:
    output = BrainOutput(
        brain="context",
        output_type="WATCH",
        recommendation="WATCH",
        confidence=0.72,
        urgency=0.4,
        risk_flags=["resolution_ambiguous"],
        reasoning_summary="Rules ambiguity was observed.",
        status="ACTIVE",
    )

    assert output.brain_output_id.startswith("brain_output_")
    assert output.brain == "context"
    assert output.market_id is None
    assert output.position_id is None


@pytest.mark.parametrize("field", ["confidence", "urgency"])
@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_reject_invalid_confidence_or_urgency(field: str, value: float) -> None:
    payload = {
        "brain": "risk",
        "output_type": "RISK_WARNING",
        "recommendation": "CAUTION",
        "status": "ACTIVE",
        field: value,
    }

    with pytest.raises(ValidationError):
        BrainOutput(**payload)


@pytest.mark.parametrize("field", ["brain", "output_type", "recommendation"])
def test_reject_missing_required_text(field: str) -> None:
    payload = {
        "brain": "context",
        "output_type": "WATCH",
        "recommendation": "WATCH",
        "status": "ACTIVE",
    }
    payload[field] = ""

    with pytest.raises(ValidationError):
        BrainOutput(**payload)


def test_brain_output_can_exist_without_market_or_position() -> None:
    output = BrainOutput(brain="memory", output_type="MEMORY_NOTE", recommendation="WATCH", status="ACTIVE")

    assert output.market_id is None
    assert output.position_id is None


@pytest.mark.parametrize("recommendation", ["BUY", "SELL", "ENTER_TRADE", "EXIT_TRADE", "PLACE_ORDER"])
def test_reject_executable_recommendations(recommendation: str) -> None:
    with pytest.raises(ValidationError):
        BrainOutput(
            brain="strategy",
            output_type="STRATEGY_HINT",
            recommendation=recommendation,
            status="ACTIVE",
        )


def test_reject_executable_metadata_keys() -> None:
    with pytest.raises(ValidationError):
        BrainOutput(
            brain="ai",
            output_type="AI_ANALYSIS",
            recommendation="WATCH",
            status="ACTIVE",
            metadata={"nested": {"place_order": True}},
        )


def test_dependency_and_conflict_contracts_validate_ranges() -> None:
    BrainOutputDependency(dependency_type="signal", dependency_id="signal_a", confidence=1.0)
    BrainOutputConflict(
        conflicts_with_type="signal",
        conflicts_with_id="signal_b",
        conflict_type="interpretation_mismatch",
        conflict_severity=0.25,
    )

    with pytest.raises(ValidationError):
        BrainOutputDependency(dependency_type="signal", dependency_id="signal_a", confidence=1.2)
    with pytest.raises(ValidationError):
        BrainOutputConflict(
            conflicts_with_type="signal",
            conflicts_with_id="signal_b",
            conflict_type="interpretation_mismatch",
            conflict_severity=-0.1,
        )
