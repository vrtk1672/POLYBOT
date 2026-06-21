from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_dialogue_sources


def test_system_on_materializes_dialogue_from_real_source_records(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()

    result = BrainDialogueService().materialize_recent(limit_per_source=10)

    assert result["status"] == "OK"
    assert result["events_created"] > 0
    feed = BrainDialogueService().list_events(limit=100)
    components = {event["component"] for event in feed["events"]}
    assert "MarketService" in components
    assert "DataFoundation" in components
    assert "Brain Mesh Activation" in components
    assert "Evidence Refresh" in components
    assert "Side Evidence" in components
    assert "Risk Gate" in components
    assert "Exit Cortex" in components
    assert "Eligibility Gate" in components
    assert all(event["source_table"] and event["source_record_id"] for event in feed["events"])
    assert all(event["human_message"] for event in feed["events"])


def test_system_off_blocks_normal_dialogue_generation(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    SystemPowerService().turn_off(actor="test", reason="dialogue_off", correlation_id="dialogue-off")

    result = BrainDialogueService().materialize_recent(limit_per_source=10)

    assert result["status"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        normal_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_dialogue_events
            WHERE component <> 'SystemPower'
            """
        ).fetchone()["count"]
        system_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_dialogue_events
            WHERE component = 'SystemPower'
            """
        ).fetchone()["count"]
    assert normal_count == 0
    assert system_count >= 1


def test_no_source_records_produces_no_fake_component_dialogue(postgres_test_schema) -> None:
    prepare_brain_dialogue()

    result = BrainDialogueService().materialize_recent(limit_per_source=10)

    assert result["events_created"] >= 1
    feed = BrainDialogueService().list_events(limit=100)
    assert {event["component"] for event in feed["events"]} == {"SystemPower"}
