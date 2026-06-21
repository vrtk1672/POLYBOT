from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.signal_processing_routes import create_signal_processing_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_signal_processing_router())
    return TestClient(app)


def _prepare() -> dict[str, object]:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM neuron_signals")
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="market",
            event_type="source_status_observed",
            source_name="polymarket_gamma",
            status="ACTIVE",
            market_id="processing-api-market",
            confidence=0.8,
            strength=0.8,
            evidence={"runtime_status": "ACTIVE"},
        )
    )


def test_post_evaluate_recent_and_get_recent_processing(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        evaluated = client.post("/signals/processing/evaluate/recent", json={"limit": 100, "refresh_quality": False}).json()
        recent = client.get("/signals/processing/recent").json()

    assert evaluated["mock_data"] is False
    assert evaluated["evaluated"] == 1
    assert evaluated["summary"]["paper_ready"] is False
    assert recent["mock_data"] is False
    assert recent["count"] == 1


def test_get_and_evaluate_one_signal_processing(postgres_test_schema) -> None:
    signal = _prepare()

    with _client() as client:
        response = client.post(f"/signals/{signal['signal_id']}/processing/evaluate", json={"refresh_quality": False})
        get_response = client.get(f"/signals/{signal['signal_id']}/processing")

    payload = response.json()
    loaded = get_response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["processing"]["signal_id"] == signal["signal_id"]
    assert loaded["status"] == "OK"
    assert loaded["processing"]["gate_status"] == "NOT_EVALUATED"


def test_empty_processing_list_is_honest(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM neuron_signals")

    with _client() as client:
        payload = client.get("/signals/processing/recent").json()

    assert payload == {"status": "OK", "mock_data": False, "count": 0, "processing": []}
