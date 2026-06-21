from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_bus.errors import NeuralDeliveryBlocked, NeuralPublishBlocked
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType
from app.services.brain_dialogue import BrainDialogueService
from app.services.system_power import SystemPowerService


def _service(postgres_test_schema) -> NeuralEventBusService:
    run_migrations()
    return NeuralEventBusService()


def test_neural_event_creation_and_persistence(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)

    event = service.publish_event(
        NeuralEventType.NEWS_DETECTED,
        source_component="News Neuron",
        source_type="neuron",
        market_id="m-news",
        correlation_id="corr-news",
        payload={"headline": "source backed"},
    )

    assert event["event_type"] == "NEWS_DETECTED"
    assert event["market_id"] == "m-news"
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM neural_events WHERE event_id = %s", (event["event_id"],)).fetchone()
    assert row is not None
    assert row["payload_json"]["headline"] == "source backed"


def test_neural_consumer_registration_and_delivery_tracking(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    service.register_consumer(
        consumer_name="risk-organ",
        event_types=[NeuralEventType.RISK_CHANGED, NeuralEventType.NEWS_DETECTED],
    )
    service.publish_event(
        NeuralEventType.RISK_CHANGED,
        source_component="Risk",
        source_type="risk",
        candidate_id="candidate-1",
        payload={"decision": "BLOCK"},
    )

    result = service.deliver_pending(limit=10)

    assert result["deliveries_recorded"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        delivery = conn.execute("SELECT * FROM neural_event_delivery WHERE consumer_name = 'risk-organ'").fetchone()
    assert delivery["delivery_status"] == "DELIVERED"


def test_neural_event_replay_by_event_type_market_and_correlation(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    service.register_consumer(consumer_name="news-organ", event_types=[NeuralEventType.NEWS_DETECTED])
    service.publish_event(
        NeuralEventType.NEWS_DETECTED,
        source_component="News Neuron",
        source_type="neuron",
        market_id="m-replay",
        correlation_id="corr-replay",
        payload={"headline": "replayable"},
    )
    service.publish_event(
        NeuralEventType.WHALE_DETECTED,
        source_component="Whale Neuron",
        source_type="neuron",
        market_id="m-replay",
        correlation_id="corr-replay",
        payload={"wallet": "0xabc"},
    )

    result = service.replay_events(
        requested_by="pytest",
        reason="filter check",
        event_type=NeuralEventType.NEWS_DETECTED,
        market_id="m-replay",
        correlation_id="corr-replay",
    )

    assert result["matched_count"] == 1
    assert result["delivered_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        replay = conn.execute("SELECT * FROM neural_event_replay WHERE replay_id = %s", (result["replay_id"],)).fetchone()
    assert replay["status"] == "COMPLETED"
    assert replay["filter_json"]["event_type"] == "NEWS_DETECTED"


def test_system_off_blocks_publish_and_delivery(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    SystemPowerService().turn_off(actor="pytest", reason="off blocks neural bus")

    with pytest.raises(NeuralPublishBlocked):
        service.publish_event(
            NeuralEventType.MARKET_REPRICING,
            source_component="Market Neuron",
            source_type="market",
            payload={"price": 0.5},
        )
    with pytest.raises(NeuralDeliveryBlocked):
        service.deliver_pending(limit=10)

    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM neural_events").fetchone()["count"]
    assert count == 0


def test_system_on_allows_publish_after_off(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    power = SystemPowerService()
    power.turn_off(actor="pytest", reason="off first")
    power.turn_on(actor="pytest", reason="on permits neural bus")

    event = service.publish_event(
        NeuralEventType.LIQUIDITY_CHANGED,
        source_component="Liquidity Neuron",
        source_type="neuron",
        market_id="m-liq",
        payload={"liquidity": 123.45},
    )

    assert event["event_type"] == "LIQUIDITY_CHANGED"


def test_dashboard_truth_and_no_live_or_paper_impact(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    service.register_consumer(consumer_name="eligibility-organ", event_types=[NeuralEventType.ELIGIBILITY_CHANGED])
    service.publish_event(
        NeuralEventType.ELIGIBILITY_CHANGED,
        source_component="Eligibility",
        source_type="eligibility",
        candidate_id="candidate-dashboard",
        payload={"status": "BLOCKED"},
    )
    service.deliver_pending(limit=10)

    payload = service.dashboard_summary(limit=10)

    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["events_last_day"] >= 1
    assert payload["active_consumers"] == 1
    assert payload["failed_deliveries"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        live_orders = conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]
        paper_orders = conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]
        paper_positions = conn.execute("SELECT COUNT(*) AS count FROM paper_positions").fetchone()["count"]
    assert live_orders == 0
    assert paper_orders == 0
    assert paper_positions == 0


def test_neural_event_dialogue_visibility_is_source_backed(postgres_test_schema) -> None:
    service = _service(postgres_test_schema)
    event = service.publish_event(
        NeuralEventType.ORDERBOOK_REFRESHED,
        source_component="Orderbook",
        source_type="neuron",
        market_id="m-book",
        source_table="orderbook_snapshots",
        source_record_id="snapshot-1",
        payload={"snapshot_status": "OK"},
    )

    result = BrainDialogueService().materialize_recent(limit_per_source=20)
    feed = BrainDialogueService().list_events(limit=20)

    assert result["status"] == "OK"
    messages = [row["human_message"] for row in feed["events"]]
    assert any("Orderbook: Published ORDERBOOK_REFRESHED" in message for message in messages)
    assert any(row["source_table"] == "neural_events" and row["source_record_id"] == event["event_id"] for row in feed["events"])
