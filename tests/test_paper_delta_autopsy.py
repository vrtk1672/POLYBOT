from __future__ import annotations

from app.services.decision_autopsy import DecisionAutopsyService
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_delta_run


def test_paper_activity_delta_in_paper_mode_is_expected(postgres_test_schema) -> None:
    prepare_autopsy_fixture(mode="PAPER")
    seed_delta_run()

    payload = DecisionAutopsyService().paper_delta_autopsy()

    assert payload["items"][0]["classification"] == "EXPECTED_ACTIVITY"
    assert payload["items"][0]["severity"] == "INFO"
    assert payload["latest_errors_should_include_expected_paper_activity"] is False


def test_paper_activity_delta_in_data_only_is_suspicious(postgres_test_schema) -> None:
    prepare_autopsy_fixture(mode="DATA_ONLY")
    seed_delta_run()

    payload = DecisionAutopsyService().paper_delta_autopsy()

    assert payload["items"][0]["classification"] == "SUSPICIOUS_ACTIVITY"
    assert payload["items"][0]["severity"] == "ERROR"
