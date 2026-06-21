from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.connection import DatabaseConnectionFactory
from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService

from brain_dialogue_fixtures import prepare_brain_dialogue, seed_neuron_dialogue_sources


def test_system_life_returns_neuron_coverage_summary(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/system-life")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_neurons"] >= 12
    assert payload["neuron_components_speaking"] > 0
    assert "neuron_coverage" in payload
    neurons = {item["component"]: item for item in payload["neuron_coverage"]["neurons"]}
    assert neurons["Orderbook Neuron"]["active"] is True
    assert neurons["Orderbook Neuron"]["wired"] is True
    assert neurons["Orderbook Neuron"]["events_24h"] > 0
    assert neurons["Capital Neuron"]["active"] is False
    assert neurons["Capital Neuron"]["silent_reason"]


def test_decorative_service_health_does_not_make_neuron_active(postgres_test_schema) -> None:
    prepare_brain_dialogue()
    seed_neuron_dialogue_sources()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, updated_at)
            VALUES ('Capital Neuron', 'neuron', 'RUNNING', now())
            ON CONFLICT (service_name) DO UPDATE SET status='RUNNING', updated_at=now()
            """
        )
    BrainDialogueService().materialize_recent(limit_per_source=20)

    life = BrainDialogueService().get_system_life()
    neurons = {item["component"]: item for item in life["neuron_coverage"]["neurons"]}

    assert neurons["Capital Neuron"]["active"] is False
    assert neurons["Capital Neuron"]["events_24h"] == 0
