from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_dialogue_sources


def test_system_life_screen_api_returns_component_truth(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/system-life")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["system_power"] == "ON"
    assert payload["active_components"] > 0
    assert payload["live_orders"] == 0
    assert payload["real_orders"] == 0
    components = {component["component"]: component for component in payload["components"]}
    assert components["MarketService"]["active"] is True
    assert components["Risk Gate"]["wired"] is True
    assert "latest_message" in components["Risk Gate"]
