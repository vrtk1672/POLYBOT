from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_dialogue_sources


def test_dashboard_reads_do_not_create_duplicate_dialogue_events(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    service = BrainDialogueService()

    first = service.materialize_recent(limit_per_source=20)
    second = service.materialize_recent(limit_per_source=20)
    service.list_events(limit=20)
    service.list_events(limit=20)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM brain_dialogue_events").fetchone()["count"]
    assert first["events_created"] > 0
    assert second["events_created"] == 0
    assert count == first["events_created"]


def test_risk_exit_eligibility_and_no_trade_dialogue_are_source_backed(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)

    feed = BrainDialogueService().list_events(limit=100)
    by_component = {event["component"]: event for event in feed["events"]}

    assert by_component["Risk Gate"]["source_table"] == "risk_decisions"
    assert "Risk Gate:" in by_component["Risk Gate"]["human_message"]
    assert by_component["Exit Cortex"]["source_table"] == "exit_plans"
    assert "Exit Cortex:" in by_component["Exit Cortex"]["human_message"]
    assert by_component["Eligibility Gate"]["source_table"] == "paper_eligibility_candidates"
    assert "Eligibility Gate:" in by_component["Eligibility Gate"]["human_message"]
