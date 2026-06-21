from __future__ import annotations

from decimal import Decimal

from app.services.paper_defense import apply_defense_to_blockers, defense_profile, policy_for


def test_integrity_blockers_remain_hard_at_defense_zero() -> None:
    result = apply_defense_to_blockers(
        blockers=["MISSING_TOKEN_ID", "THESIS_NOT_SUPPORTED"],
        warnings=[],
        score=Decimal("80"),
        profile=defense_profile(0),
    )
    assert "MISSING_TOKEN_ID" in result["effective_blockers"]
    assert "THESIS_NOT_SUPPORTED" in result["ignored_blockers"]


def test_score_blocker_can_be_ignored_at_low_defense() -> None:
    result = apply_defense_to_blockers(
        blockers=["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
        warnings=[],
        score=Decimal("55.46"),
        profile=defense_profile(20),
    )
    assert result["effective_blockers"] == []
    assert "OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD" in result["ignored_blockers"]
    assert result["effective_verdict"] == "ALLOWED_FOR_LEARNING"


def test_exit_not_ready_requires_fallback_exit() -> None:
    result = apply_defense_to_blockers(
        blockers=["EXIT_NOT_READY"],
        warnings=[],
        score=Decimal("55"),
        profile=defense_profile(20),
    )
    assert result["effective_blockers"] == []
    assert "EXIT_NOT_READY" in result["fallback_requirements"]
    assert result["fallback_exit"]["exit_plan_type"] == "FALLBACK_LEARNING"


def test_unmapped_blockers_are_visible_not_hidden() -> None:
    policy = policy_for("NEW_STRATEGIC_BLOCKER")
    assert policy.owner_gate == "UNMAPPED"
    assert policy.can_soften is True
