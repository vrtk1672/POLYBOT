from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import create_app
from app.neural_bus.service import NeuralEventBusService
from app.neural_bus.types import NeuralEventType


def test_dashboard_neural_bus_returns_truth(postgres_test_schema) -> None:
    run_migrations()
    service = NeuralEventBusService()
    service.register_consumer(consumer_name="dashboard-organ", event_types=[NeuralEventType.NEWS_DETECTED])
    service.publish_event(
        NeuralEventType.NEWS_DETECTED,
        source_component="News Neuron",
        source_type="neuron",
        market_id="dashboard-market",
        payload={"headline": "dashboard truth"},
    )
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/neural-bus?limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["events_last_day"] >= 1
    assert payload["active_consumers"] == 1
    assert any(item["event_type"] == "NEWS_DETECTED" for item in payload["event_types"])
    assert payload["latest_events"][0]["payload_json"]["headline"] == "dashboard truth"
