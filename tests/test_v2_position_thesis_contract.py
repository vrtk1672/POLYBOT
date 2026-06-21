from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.neural_mesh.position_thesis import PositionThesisProfile, calculate_thesis_validation


def _paper_ready_profile(**overrides) -> PositionThesisProfile:
    data = {
        "position_id": "position-contract",
        "market_id": "market-contract",
        "side": "UNKNOWN",
        "entry_thesis": "Documented asymmetric thesis with defined downside.",
        "profit_drivers": ["clear resolution path"],
        "invalidation_drivers": ["resolution source becomes ambiguous"],
        "danger_signals": ["rules_degraded"],
        "take_profit_rules": ["review profit if market reprices materially"],
        "emergency_exit_rules": ["review immediately if resolution source is invalidated"],
        "status": "ACTIVE",
    }
    data.update(overrides)
    return PositionThesisProfile(**data).with_validation()


def test_create_valid_thesis_profile_contract() -> None:
    profile = _paper_ready_profile()

    assert profile.thesis_id.startswith("thesis_")
    assert profile.paper_ready is True
    assert profile.live_ready is False
    assert 0 <= profile.completeness_score <= 1


def test_reject_empty_entry_thesis_for_active() -> None:
    with pytest.raises(ValidationError):
        _paper_ready_profile(entry_thesis="   ")


def test_calculate_completeness_score() -> None:
    validation = calculate_thesis_validation(_paper_ready_profile())

    assert validation.paper_ready is True
    assert validation.live_ready is False
    assert validation.completeness_score > 0.5


def test_paper_ready_false_when_invalidation_missing() -> None:
    profile = _paper_ready_profile(invalidation_drivers=[])
    validation = calculate_thesis_validation(profile)

    assert validation.paper_ready is False
    assert "invalidation_drivers" in validation.missing_fields


def test_paper_ready_false_when_emergency_exit_missing() -> None:
    profile = _paper_ready_profile(emergency_exit_rules=[])
    validation = calculate_thesis_validation(profile)

    assert validation.paper_ready is False
    assert "emergency_exit_rules" in validation.missing_fields


def test_live_ready_requires_paper_ready() -> None:
    profile = _paper_ready_profile(invalidation_drivers=[], side="YES", watch_entities=["issuer"])
    validation = calculate_thesis_validation(profile)

    assert validation.paper_ready is False
    assert validation.live_ready is False


def test_live_ready_requires_side_yes_or_no() -> None:
    profile = _paper_ready_profile(
        side="UNKNOWN",
        watch_entities=["issuer"],
        partial_exit_rules=["review partial de-risk if thesis weakens"],
        reviewed_by="operator",
        reviewed_at=datetime.now(UTC),
    )
    validation = calculate_thesis_validation(profile)

    assert validation.paper_ready is True
    assert validation.live_ready is False
    assert "side_yes_or_no" in validation.missing_fields


def test_live_ready_requires_higher_completeness_threshold() -> None:
    incomplete = _paper_ready_profile(side="YES", watch_entities=[], reviewed_by="operator", reviewed_at=datetime.now(UTC))
    complete = _paper_ready_profile(
        side="YES",
        watch_entities=["issuer"],
        partial_exit_rules=["review partial de-risk if edge compresses"],
        reviewed_by="operator",
        reviewed_at=datetime.now(UTC),
    )

    assert calculate_thesis_validation(incomplete).live_ready is False
    assert calculate_thesis_validation(complete).live_ready is True


def test_reject_executable_rule_language() -> None:
    with pytest.raises(ValidationError):
        _paper_ready_profile(take_profit_rules=["PLACE_ORDER when profitable"])
