from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.link_coverage_routes import create_link_coverage_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_link_coverage_router())
    return TestClient(app)


def _prepare() -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM markets_v2")
        conn.execute(
            """
            INSERT INTO markets_v2 (market_id, question, slug)
            VALUES ('api-link-market', 'Will API link market resolve?', 'api-link-market')
            """
        )
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="api-link-market",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:api",
        )
    )


def test_post_analyze_recent_and_get_recent_link_coverage(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        analyzed = client.post("/signals/link-coverage/analyze/recent", json={"limit": 100, "create_suggestions": True, "apply_safe_links": False}).json()
        recent = client.get("/signals/link-coverage/recent?include_suggestions=true").json()

    assert analyzed["mock_data"] is False
    assert analyzed["analyzed"] == 1
    assert analyzed["applied_links"] == 0
    assert recent["mock_data"] is False
    assert recent["count"] == 1
    assert recent["link_coverage"][0]["suggestions"]


def test_get_and_analyze_one_signal_link_coverage(postgres_test_schema) -> None:
    signal = _prepare()

    with _client() as client:
        response = client.post(f"/signals/{signal['signal_id']}/link-coverage/analyze", json={"create_suggestions": True, "apply_safe_links": False})
        loaded = client.get(f"/signals/{signal['signal_id']}/link-coverage")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["link_coverage"]["suggested_link_action"] == "SAFE_TO_LINK_EXISTING_MARKET_ID"
    assert loaded.json()["link_coverage"]["signal_id"] == signal["signal_id"]


def test_empty_link_coverage_list_is_honest(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM neuron_signals")

    with _client() as client:
        payload = client.get("/signals/link-coverage/recent").json()

    assert payload == {"status": "OK", "mock_data": False, "count": 0, "link_coverage": []}
