from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_neuron_dialogue_sources


def test_orderbook_neuron_dialogue_uses_orderbook_snapshot_source(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    ids = seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)

    feed = BrainDialogueService().list_events(limit=20, component="Orderbook Neuron")

    assert feed["events"]
    event = feed["events"][0]
    assert event["source_table"] == "orderbook_snapshots"
    assert event["source_record_id"] == ids["orderbook_id"]
    assert event["market_id"] == ids["market_id"]
    assert "best_bid" in event["human_message"]
    assert event["evidence_used_json"]["mid_price"] == 0.42


def test_market_time_liquidity_fee_rules_neurons_use_distinct_sources(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)

    feed = BrainDialogueService().list_events(limit=100, component_type="neuron")
    source_by_component = {event["component"]: event["source_table"] for event in feed["events"]}

    assert source_by_component["Market Neuron"] == "market_snapshots"
    assert source_by_component["Time Neuron"] == "market_snapshots"
    assert source_by_component["Liquidity Neuron"] == "liquidity_snapshots"
    assert source_by_component["Fees / Rewards Neuron"] == "fee_snapshots"
    assert source_by_component["Rules / Wording Neuron"] == "rules_analysis"


def test_dashboard_reads_do_not_materialize_neuron_events(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)

    with DatabaseConnectionFactory().connect() as conn:
        before = conn.execute("SELECT COUNT(*) AS count FROM brain_dialogue_events WHERE component_type = 'neuron'").fetchone()["count"]
    BrainDialogueService().list_events(limit=20, component_type="neuron")
    BrainDialogueService().get_system_life()
    BrainDialogueService().get_neuron_dialogue(limit=20)
    with DatabaseConnectionFactory().connect() as conn:
        after = conn.execute("SELECT COUNT(*) AS count FROM brain_dialogue_events WHERE component_type = 'neuron'").fetchone()["count"]

    assert after == before
