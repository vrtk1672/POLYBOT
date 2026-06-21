from __future__ import annotations

from app.runtime.mode_manager import ModeManager
from app.runtime.modes import RuntimeMode


def _evaluate(from_mode: RuntimeMode, to_mode: RuntimeMode, **metadata):
    return ModeManager().evaluate_transition(
        from_mode=from_mode,
        to_mode=to_mode,
        actor="operator",
        reason="test transition",
        metadata=metadata,
    )


def test_data_only_to_paper_allowed() -> None:
    assert _evaluate(RuntimeMode.DATA_ONLY, RuntimeMode.PAPER).allowed


def test_paper_to_shadow_live_allowed() -> None:
    assert _evaluate(RuntimeMode.PAPER, RuntimeMode.SHADOW_LIVE).allowed


def test_shadow_to_small_live_blocked_without_certification() -> None:
    result = _evaluate(RuntimeMode.SHADOW_LIVE, RuntimeMode.SMALL_LIVE)
    assert not result.allowed
    assert "certification" in result.required_metadata


def test_shadow_to_small_live_allowed_with_certification() -> None:
    assert _evaluate(RuntimeMode.SHADOW_LIVE, RuntimeMode.SMALL_LIVE, certification=True).allowed


def test_any_to_kill_allowed() -> None:
    for mode in RuntimeMode:
        assert _evaluate(mode, RuntimeMode.KILL).allowed


def test_kill_to_data_only_allowed_with_reason() -> None:
    assert _evaluate(RuntimeMode.KILL, RuntimeMode.DATA_ONLY).allowed


def test_kill_to_small_live_blocked() -> None:
    assert not _evaluate(RuntimeMode.KILL, RuntimeMode.SMALL_LIVE).allowed


def test_empty_reason_blocked() -> None:
    result = ModeManager().evaluate_transition(
        from_mode=RuntimeMode.DATA_ONLY,
        to_mode=RuntimeMode.PAPER,
        actor="operator",
        reason="",
    )
    assert not result.allowed
    assert result.blocked_reason == "reason is required"


def test_empty_actor_blocked() -> None:
    result = ModeManager().evaluate_transition(
        from_mode=RuntimeMode.DATA_ONLY,
        to_mode=RuntimeMode.PAPER,
        actor="",
        reason="reason",
    )
    assert not result.allowed
    assert result.blocked_reason == "actor is required"


def test_attack_mode_blocked_without_governor_approval() -> None:
    result = _evaluate(RuntimeMode.PAPER, RuntimeMode.ATTACK_MODE)
    assert not result.allowed
    assert "governor_approved" in result.required_metadata
