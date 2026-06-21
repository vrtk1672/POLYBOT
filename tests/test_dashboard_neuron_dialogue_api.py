from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_neuron_dialogue_sources


def test_brain_dialogue_api_filters_component_type_neuron(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/brain-dialogue?component_type=neuron&limit=50")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["events"]
    assert {event["component_type"] for event in payload["events"]} == {"neuron"}
    assert payload["safety"]["live_orders"] == 0
    assert payload["safety"]["real_orders"] == 0


def test_neuron_dialogue_endpoint_returns_status_summary(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/neuron-dialogue?limit=50")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["events"]
    assert payload["total_neurons"] >= 12
    assert payload["speaking_neurons"] > 0
    assert payload["per_neuron_status"]


def test_neuron_dialogue_endpoint_filters_component(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/neuron-dialogue?component=Orderbook%20Neuron")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert {event["component"] for event in payload["events"]} == {"Orderbook Neuron"}
