from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_neuron_dialogue_sources


def _paper_counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            "paper_intents": conn.execute("SELECT COUNT(*) AS count FROM paper_intents").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "paper_fills": conn.execute("SELECT COUNT(*) AS count FROM paper_fills").fetchone()["count"],
            "paper_positions": conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"],
        }


def test_neuron_dialogue_does_not_create_trading_artifacts(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    before = _paper_counts()

    BrainDialogueService().materialize_recent(limit_per_source=20)

    after = _paper_counts()
    assert after["paper_intents"] == before["paper_intents"]
    assert after["paper_orders"] == before["paper_orders"]
    assert after["paper_fills"] == before["paper_fills"]
    assert after["paper_positions"] == before["paper_positions"]


def test_off_then_on_only_creates_neuron_dialogue_when_on(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    SystemPowerService().turn_off(actor="test", reason="neuron_off", correlation_id="neuron-off")

    BrainDialogueService().materialize_recent(limit_per_source=20)
    with DatabaseConnectionFactory().connect() as conn:
        off_count = conn.execute("SELECT COUNT(*) AS count FROM brain_dialogue_events WHERE component_type='neuron'").fetchone()["count"]
    SystemPowerService().turn_on(actor="test", reason="neuron_on", correlation_id="neuron-on")
    BrainDialogueService().materialize_recent(limit_per_source=20)
    with DatabaseConnectionFactory().connect() as conn:
        on_count = conn.execute("SELECT COUNT(*) AS count FROM brain_dialogue_events WHERE component_type='neuron'").fetchone()["count"]

    assert off_count == 0
    assert on_count > 0
