from app.services.paper_observation_policy import (
    OBSERVATION_POLICY_INCOMPLETE,
    OBSERVATION_POLICY_WATCH,
    build_policy_review,
)
from test_paper_observation_policy_review import _row


def test_thesis_watch_hard_blocked_mesh_row_becomes_watch_not_fake_eligible():
    review = build_policy_review(
        _row(
            market_id="597967",
            side="NO",
            opportunity_decision_band="HARD_BLOCKED",
            trade_thesis_state="THESIS_WATCH",
            opportunity_score=55.46,
            hard_blockers_json=["missing_dynamic_hold_time"],
        )
    )

    assert review["observation_policy_state"] == OBSERVATION_POLICY_WATCH
    assert review["observation_allowed_by_policy"] is False
    assert "decision_band_not_paper_observation" in review["policy_blockers_json"]
    assert "thesis_watch_not_observation_policy_eligible" in review["policy_blockers_json"]
    assert "existing_hard_blockers_present" in review["policy_blockers_json"]


def test_thesis_missing_reports_incomplete_required_to_pass():
    review = build_policy_review(
        _row(
            market_id="666655",
            side="NO",
            opportunity_decision_band="HARD_BLOCKED",
            trade_thesis_state="THESIS_MISSING",
            exit_state="EXIT_NOT_READY",
            opportunity_score=46.3,
            hard_blockers_json=["missing_trade_thesis", "exit_not_ready"],
        )
    )

    assert review["observation_policy_state"] == OBSERVATION_POLICY_INCOMPLETE
    assert review["observation_allowed_by_policy"] is False
    assert "thesis_not_supported" in review["policy_blockers_json"]
    assert "exit_not_ready" in review["policy_blockers_json"]
