from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.signal_routes import create_signal_router
from app.db.connection import DatabaseConnectionFactory
from app.services.neuron_signals import NeuronSignalService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_signal_router())
    return TestClient(app)


def test_signal_lineage_api_returns_lineage(postgres_test_schema) -> None:
    _clear()
    created = NeuronSignalService().create_signal_with_lineage(
        {"neuron": "rules", "event_type": "rules_resolution_status_observed", "status": "ACTIVE", "correlation_id": "corr-api"},
        {"producer_name": "rules_resolution_adapter", "generated_from": "rules_resolution", "correlation_id": "corr-api"},
    )
    with _client() as client:
        response = client.get(f"/signals/{created['signal_id']}/lineage")
    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["lineage"]["producer_name"] == "rules_resolution_adapter"


def test_signal_lineage_query_apis(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().create_signal_with_lineage(
        {
            "neuron": "market",
            "event_type": "source_status_observed",
            "source_name": "polymarket_gamma",
            "status": "ACTIVE",
            "correlation_id": "corr-query",
        },
        {
            "producer_name": "source_status_adapter",
            "source_name": "polymarket_gamma",
            "generated_from": "source_status",
            "correlation_id": "corr-query",
        },
    )
    with _client() as client:
        by_corr = client.get("/signals/correlation/corr-query").json()
        by_source = client.get("/signals/source/polymarket_gamma").json()
        by_producer = client.get("/signals/producer/source_status_adapter").json()
    assert by_corr["count"] == 1
    assert by_source["count"] == 1
    assert by_producer["count"] == 1
