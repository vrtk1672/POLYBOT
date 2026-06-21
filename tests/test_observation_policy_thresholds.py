from app.services.paper_observation_policy import (
    OBSERVATION_POLICY_BLOCKED,
    OBSERVATION_POLICY_WATCH,
    build_policy_review,
    observation_policy_thresholds,
)
from test_paper_observation_policy_review import _row


def test_thesis_watch_becomes_watch_not_automatically_eligible():
    review = build_policy_review(_row(trade_thesis_state="THESIS_WATCH"))

    assert review["observation_policy_state"] == OBSERVATION_POLICY_WATCH
    assert review["observation_allowed_by_policy"] is False
    assert "thesis_watch_not_observation_policy_eligible" in review["policy_blockers_json"]


def test_score_below_observation_threshold_blocks_policy():
    review = build_policy_review(_row(opportunity_score=59.9))

    assert review["observation_policy_state"] == OBSERVATION_POLICY_BLOCKED
    assert "opportunity_score_below_observation_threshold" in review["policy_blockers_json"]


def test_thresholds_preserve_risk_and_capital_watch_as_review_only():
    thresholds = observation_policy_thresholds()

    assert thresholds["risk_review_allowed_for_observation"] is True
    assert thresholds["capital_watch_allowed_for_observation"] is True
    assert thresholds["risk_blocked_blocks_observation"] is True
    assert thresholds["capital_blocked_blocks_observation"] is True
