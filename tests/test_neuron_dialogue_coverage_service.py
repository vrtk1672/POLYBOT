from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_neuron_dialogue_sources


def test_system_on_materializes_source_backed_neuron_dialogue(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()

    result = BrainDialogueService().materialize_recent(limit_per_source=20)

    assert result["status"] == "OK"
    feed = BrainDialogueService().list_events(limit=100, component_type="neuron")
    components = {event["component"] for event in feed["events"]}
    assert "Market Neuron" in components
    assert "Orderbook Neuron" in components
    assert "Liquidity Neuron" in components
    assert "Time Neuron" in components
    assert "Rules / Wording Neuron" in components
    assert "Fees / Rewards Neuron" in components
    assert "News Neuron" in components
    assert "Social / Hype Neuron" in components
    assert "Whale Neuron" in components
    assert "AI / Context Neuron" in components
    assert "Position Neuron" in components
    assert all(event["component_type"] == "neuron" for event in feed["events"])
    assert all(event["source_table"] and event["source_record_id"] for event in feed["events"])
    assert all(event["human_message"] for event in feed["events"])


def test_system_off_blocks_normal_neuron_dialogue_materialization(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    SystemPowerService().turn_off(actor="test", reason="neuron_dialogue_off", correlation_id="neuron-off")

    result = BrainDialogueService().materialize_recent(limit_per_source=20)

    assert result["status"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_dialogue_events
            WHERE component_type = 'neuron'
            """
        ).fetchone()["count"]
    assert count == 0


def test_repeated_materialization_does_not_duplicate_neuron_events(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    service = BrainDialogueService()

    first = service.materialize_recent(limit_per_source=20)
    second = service.materialize_recent(limit_per_source=20)

    assert first["events_created"] > 0
    assert second["events_created"] == 0


def test_silent_neurons_are_not_counted_active(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)

    life = BrainDialogueService().get_system_life()
    by_name = {item["component"]: item for item in life["neuron_coverage"]["neurons"]}

    assert by_name["Capital Neuron"]["active"] is False
    assert by_name["Capital Neuron"]["status"] in {"SILENT_NO_SOURCE_RECORD", "MISSING_SOURCE", "SILENT_STALE"}
    assert by_name["Capital Neuron"]["silent_reason"]
