from __future__ import annotations

from app.services.decision_autopsy import DecisionAutopsyService
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_runtime_decision


def test_watch_decision_reports_score_threshold_and_expected_block(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-watch-score",
        market_id="m-watch",
        side="NO",
        decision="WATCH",
        score=55.46,
        blockers=["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"],
    )

    item = DecisionAutopsyService().list_autopsies(limit=5)["items"][0]

    assert item["blocker_codes"] == ["OPPORTUNITY_SCORE_BELOW_PAPER_THRESHOLD"]
    assert item["observed_values"]["opportunity_score"] == 55.46
    assert item["required_values"]["opportunity_score_min"] == 60.0
    assert item["is_expected_block"] is True
    assert item["is_bug_suspect"] is False
