from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.neuron_routes import create_neuron_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _clear_mesh() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM neuron_health")
        conn.execute("DELETE FROM source_status")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_neuron_router())
    return TestClient(app)


def test_neurons_api_returns_truth(postgres_test_schema) -> None:
    _clear_mesh()
    with _client() as client:
        response = client.get("/neurons")
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "OK"
    assert payload["mock_data"] is False
    assert payload["count"] >= 15


def test_neuron_detail_returns_one_neuron(postgres_test_schema) -> None:
    _clear_mesh()
    NeuronSignalService().create_signal(
        NeuronSignal(neuron="orderbook", event_type="source_status_observed", status="ACTIVE", raw_direction="neutral")
    )
    with _client() as client:
        response = client.get("/neurons/orderbook")
    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["neuron"]["neuron_name"] == "orderbook"
    assert payload["neuron"]["health"]["health_status"] == "ACTIVE"


def test_neurons_api_filters_status(postgres_test_schema) -> None:
    _clear_mesh()
    with _client() as client:
        payload = client.get("/neurons?status=DISABLED").json()
    names = {item["neuron_name"] for item in payload["neurons"]}
    assert {"news", "social"} <= names
