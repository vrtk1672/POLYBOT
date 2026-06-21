from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.lineage_coverage_routes import create_lineage_coverage_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.lineage import SignalLineage
from app.repositories.signal_lineage_repository import SignalLineageRepository
from app.services.neuron_signals import NeuronSignalService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_lineage_coverage_router())
    return TestClient(app)


def _prepare() -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_lineage_coverage_runs")
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="api-lineage-signal",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:api",
            correlation_id="corr-api-lineage",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalLineageRepository().attach_signal_binding(
            conn,
            SignalLineage(
                signal_id=str(signal["signal_id"]),
                neuron_name="rules",
                producer_name="rules_resolution_adapter",
                source_name="rules_resolution_truth",
                source_event_id="evt-api",
                correlation_id="corr-api-lineage",
                raw_payload_ref="rules:api",
                generated_from="rules_resolution",
                lineage={"raw_payload_policy": "reference_only"},
            ),
        )
    return signal


def test_post_analyze_recent_and_get_recent_lineage_coverage(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        analyzed = client.post("/signals/lineage-coverage/analyze/recent", json={"limit": 100}).json()
        recent = client.get("/signals/lineage-coverage/recent").json()

    assert analyzed["mock_data"] is False
    assert analyzed["analyzed"] == 1
    assert recent["mock_data"] is False
    assert recent["count"] == 1
    assert recent["lineage_coverage"][0]["signal_id"] == "api-lineage-signal"


def test_get_and_analyze_one_signal_lineage_coverage(postgres_test_schema) -> None:
    signal = _prepare()

    with _client() as client:
        response = client.post(f"/signals/{signal['signal_id']}/lineage-coverage/analyze")
        loaded = client.get(f"/signals/{signal['signal_id']}/lineage-coverage")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["status"] == "OK"
    assert payload["lineage_coverage"]["lineage_status"] in {"COMPLETE", "RUNTIME_VERIFIED"}
    assert loaded.json()["lineage_coverage"]["signal_id"] == signal["signal_id"]


def test_empty_lineage_coverage_list_is_honest(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM neuron_signals")

    with _client() as client:
        payload = client.get("/signals/lineage-coverage/recent").json()

    assert payload == {"status": "OK", "mock_data": False, "count": 0, "lineage_coverage": []}
