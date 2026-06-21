from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mesh_dry_run_routes import create_mesh_dry_run_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM mesh_dry_run_items")
        conn.execute("DELETE FROM mesh_dry_runs")
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_mesh_dry_run_router())
    return TestClient(app)


def test_mesh_dry_run_api_posts_and_reads_runs(postgres_test_schema) -> None:
    _prepare()
    NeuronSignalService().create_signal(
        NeuronSignal(neuron="rules", event_type="rules", status="DEGRADED", market_id="api-market")
    )

    with _client() as client:
        created = client.post("/mesh/dry-run/first-intelligence", json={"limit": 10, "dry_run_only": True}).json()
        recent = client.get("/mesh/dry-runs/recent").json()
        one = client.get(f"/mesh/dry-runs/{created['dry_run_id']}").json()

    assert created["mock_data"] is False
    assert created["execution_allowed"] is False
    assert created["orders_created"] == 0
    assert recent["count"] == 1
    assert one["dry_run"]["dry_run_id"] == created["dry_run_id"]


def test_mesh_dry_run_api_filters_market(postgres_test_schema) -> None:
    _prepare()
    NeuronSignalService().create_signal(
        NeuronSignal(neuron="rules", event_type="rules", status="DEGRADED", market_id="included-market")
    )
    NeuronSignalService().create_signal(
        NeuronSignal(neuron="rules", event_type="rules", status="DEGRADED", market_id="other-market")
    )

    with _client() as client:
        created = client.post(
            "/mesh/dry-run/first-intelligence",
            json={"limit": 10, "market_id": "included-market", "dry_run_only": True},
        ).json()

    assert created["markets_processed"] == 1
    assert created["sample_results"][0]["market_id"] == "included-market"
