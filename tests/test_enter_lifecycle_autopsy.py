from __future__ import annotations

from app.services.decision_autopsy import DecisionAutopsyService
from decision_autopsy_helpers import prepare_autopsy_fixture, seed_enter_lifecycle, seed_runtime_decision


def test_enter_decision_reports_full_paper_lifecycle(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-enter",
        market_id="m-enter",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )
    seed_enter_lifecycle("decision-enter")

    item = DecisionAutopsyService().enter_autopsy()["items"][0]

    assert item["action"] == "ENTER"
    assert item["paper_lifecycle"]["intent_id"] == "intent-enter"
    assert item["paper_lifecycle"]["order_id"] == "33333333-3333-4333-8333-333333333333"
    assert item["paper_lifecycle"]["fill_id"] == "fill-enter"
    assert item["paper_lifecycle"]["position_id"] == "44444444-4444-4444-8444-444444444444"
    assert item["is_bug_suspect"] is False


def test_enter_without_intent_is_bug_suspect(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-enter-no-intent",
        market_id="m-no-intent",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )

    item = DecisionAutopsyService().enter_autopsy()["items"][0]

    assert "ENTER_WITHOUT_INTENT" in item["suspicion_flags"]
    assert item["is_bug_suspect"] is True
