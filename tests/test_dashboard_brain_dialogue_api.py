from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_dialogue_sources


def test_brain_dialogue_dashboard_api_returns_truth(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/brain-dialogue?limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["events"]
    assert payload["components_speaking"] > 0
    assert payload["safety"]["live_orders"] == 0
    assert payload["safety"]["real_orders"] == 0
    assert all(event["source_table"] for event in payload["events"])


def test_brain_dialogue_api_filters_by_component(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/brain-dialogue?component=Risk%20Gate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["events"]
    assert {event["component"] for event in payload["events"]} == {"Risk Gate"}
