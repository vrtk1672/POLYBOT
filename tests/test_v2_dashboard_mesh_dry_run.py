from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.mesh_dry_run_routes import create_mesh_dry_run_router
from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.mesh_dry_run import MeshDryRunService
from app.services.neuron_signals import NeuronSignalService


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM mesh_dry_run_items")
        conn.execute("DELETE FROM mesh_dry_runs")
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    app.include_router(create_mesh_dry_run_router())
    return TestClient(app)


def test_dashboard_mesh_dry_run_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        empty = client.get("/dashboard/api/v2/mesh-dry-run").json()

    assert empty["mock_data"] is False
    assert empty["latest_dry_run"] is None
    assert empty["safety"]["paper_orders"] == 0


def test_dashboard_mesh_reflects_latest_dry_run(postgres_test_schema) -> None:
    _prepare()
    NeuronSignalService().create_signal(
        NeuronSignal(neuron="rules", event_type="rules", status="DEGRADED", market_id="dash-market")
    )
    dry_run = MeshDryRunService().run_first_intelligence_dry_run(limit=10)

    with _client() as client:
        dry_run_dashboard = client.get("/dashboard/api/v2/mesh-dry-run").json()
        mesh = client.get("/dashboard/api/v2/mesh").json()

    assert dry_run_dashboard["mock_data"] is False
    assert dry_run_dashboard["latest_dry_run"]["dry_run_id"] == dry_run["dry_run_id"]
    assert mesh["mock_data"] is False
    assert mesh["layers"]["dry_run"]["latest_dry_run"]["dry_run_id"] == dry_run["dry_run_id"]
    assert mesh["readiness"]["paper_ready"] is False
    assert mesh["mesh_summary"]["execution_allowed_count"] == 0
