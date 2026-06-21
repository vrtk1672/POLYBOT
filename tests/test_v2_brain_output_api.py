from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.brain_output_routes import create_brain_output_router
from app.db.connection import DatabaseConnectionFactory
from app.services.brain_outputs import BrainOutputService
from app.services.neuron_signals import NeuronSignalService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_brain_output_router())
    return TestClient(app)


def test_brain_output_api_returns_empty_truth(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        response = client.get("/brain-outputs/recent")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["count"] == 0
    assert payload["outputs"] == []


def test_brain_output_api_routes_return_outputs(postgres_test_schema) -> None:
    _clear()
    signal = NeuronSignalService().create_signal(
        {"neuron": "rules", "event_type": "rules_resolution_status_observed", "market_id": "market-api", "status": "ACTIVE"}
    )
    created = BrainOutputService().create_brain_output_with_dependencies(
        {
            "brain": "context",
            "output_type": "WATCH",
            "market_id": "market-api",
            "recommendation": "WATCH",
            "status": "ACTIVE",
        },
        dependencies=[{"dependency_type": "signal", "dependency_id": str(signal["signal_id"])}],
    )

    with _client() as client:
        recent = client.get("/brain-outputs/recent").json()
        one = client.get(f"/brain-outputs/{created['brain_output_id']}").json()
        by_market = client.get("/brain-outputs/market/market-api").json()
        by_brain = client.get("/brain-outputs/brain/context").json()
        by_signal = client.get(f"/brain-outputs/signal/{signal['signal_id']}").json()

    assert recent["count"] == 1
    assert one["output"]["brain_output_id"] == created["brain_output_id"]
    assert by_market["count"] == 1
    assert by_brain["count"] == 1
    assert by_signal["count"] == 1


def test_brain_output_conflicts_api(postgres_test_schema) -> None:
    _clear()
    signal = NeuronSignalService().create_signal({"neuron": "market", "event_type": "source_status_observed", "status": "ACTIVE"})
    BrainOutputService().create_brain_output_with_dependencies(
        {"brain": "risk", "output_type": "RISK_WARNING", "recommendation": "CAUTION", "status": "ACTIVE"},
        conflicts=[
            {
                "conflicts_with_type": "signal",
                "conflicts_with_id": str(signal["signal_id"]),
                "conflict_type": "source_disagreement",
                "conflict_severity": 0.4,
            }
        ],
    )

    with _client() as client:
        response = client.get("/brain-outputs/conflicts/recent")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["count"] == 1
    assert payload["conflicts"][0]["conflict_type"] == "source_disagreement"
