from __future__ import annotations

from pydantic import ValidationError

from app.neural_mesh.signal_processing import SignalProcessingState
from app.services.signal_processing import evaluate_processing_context


def _context(**overrides):
    base = {
        "signal_id": "signal_processing_contract",
        "linked_to_market": False,
        "linked_to_position": False,
        "used_by_brain_output": False,
        "used_by_coordinator": False,
        "quality_evaluation_id": None,
        "quality_score": None,
        "quality_status": None,
        "missing_fields_json": None,
        "can_feed_brain": None,
        "can_feed_paper": None,
        "quality_linked_to_market": None,
        "quality_linked_to_position": None,
        "quality_used_by_brain_output": None,
        "quality_used_by_coordinator": None,
        "is_dry_run_generated": False,
        "is_runtime_generated": True,
        "is_stale": False,
        "evaluated_at": None,
    }
    base.update(overrides)
    return base


def test_signal_without_quality_evaluation_is_not_evaluated() -> None:
    state = evaluate_processing_context(_context())

    assert state.processing_state == "NEW"
    assert state.gate_status == "NOT_EVALUATED"
    assert state.can_feed_brain is False
    assert state.can_feed_paper is False
    assert "quality_not_evaluated" in state.gate_blockers


def test_linked_signal_without_quality_gets_linked_state() -> None:
    state = evaluate_processing_context(_context(linked_to_market=True))

    assert state.processing_state == "LINKED"
    assert state.gate_status == "NOT_EVALUATED"
    assert state.linked_to_market is True


def test_quality_checked_signal_gets_brain_eligible_gate() -> None:
    state = evaluate_processing_context(
        _context(
            quality_evaluation_id=1,
            quality_score=0.66,
            quality_status="PARTIAL",
            missing_fields_json=["linked_to_position"],
            can_feed_brain=True,
            can_feed_paper=False,
            quality_linked_to_market=True,
        )
    )

    assert state.processing_state == "QUALITY_CHECKED"
    assert state.gate_status == "BRAIN_ELIGIBLE"
    assert state.can_feed_brain is True
    assert state.can_feed_paper is False


def test_stale_signal_is_stale_and_cannot_feed_paper() -> None:
    state = evaluate_processing_context(
        _context(
            quality_evaluation_id=2,
            quality_score=0.8,
            quality_status="STALE",
            can_feed_brain=True,
            can_feed_paper=True,
            is_stale=True,
        )
    )

    assert state.processing_state == "STALE"
    assert state.gate_status == "STALE"
    assert state.can_feed_brain is False
    assert state.can_feed_paper is False


def test_paper_eligible_remains_informational_only() -> None:
    state = evaluate_processing_context(
        _context(
            quality_evaluation_id=3,
            quality_score=0.91,
            quality_status="GOOD",
            can_feed_brain=True,
            can_feed_paper=True,
            quality_linked_to_market=True,
        )
    )

    assert state.gate_status == "PAPER_ELIGIBLE_INFORMATIONAL_ONLY"
    assert state.can_feed_paper is True


def test_ignored_state_requires_ignored_reason() -> None:
    try:
        SignalProcessingState(signal_id="sig", processing_state="IGNORED", gate_status="BLOCKED")
    except ValidationError as exc:
        assert "ignored_reason" in str(exc)
    else:
        raise AssertionError("IGNORED state accepted without ignored_reason")


def test_error_state_requires_error_reason() -> None:
    try:
        SignalProcessingState(signal_id="sig", processing_state="ERROR", gate_status="ERROR")
    except ValidationError as exc:
        assert "error_reason" in str(exc)
    else:
        raise AssertionError("ERROR state accepted without error_reason")
