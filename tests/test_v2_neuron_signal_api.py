from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.signal_routes import create_signal_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_signal_router())
    return TestClient(app)


def test_signals_api_empty_db_returns_empty_truth(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        payload = client.get("/signals/recent").json()
    assert payload == {"status": "OK", "mock_data": False, "count": 0, "signals": []}


def test_signals_api_lists_recent_market_and_neuron(postgres_test_schema) -> None:
    _clear()
    service = NeuronSignalService()
    service.create_signal(
        NeuronSignal(
            neuron="market",
            event_type="source_status_observed",
            source_name="polymarket_gamma",
            market_id="market-api",
            status="ACTIVE",
            raw_direction="neutral",
        )
    )
    service.create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            market_id="market-api",
            status="DEGRADED",
            raw_direction="neutral",
        )
    )

    with _client() as client:
        recent = client.get("/signals/recent?limit=10").json()
        market = client.get("/signals/market/market-api").json()
        neuron = client.get("/signals/neuron/rules").json()

    assert recent["status"] == "OK"
    assert recent["mock_data"] is False
    assert recent["count"] == 2
    assert market["market_id"] == "market-api"
    assert market["count"] == 2
    assert neuron["neuron"] == "rules"
    assert neuron["count"] == 1
