from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.brain_outputs import BrainOutput
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM dry_run_provenance_runs")
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
    output = BrainOutputService().create_brain_output(
        BrainOutput(
            brain_output_id="dash-provenance-bo",
            brain="risk",
            output_type="RISK_WARNING",
            recommendation="NO_TRADE_HINT",
            status="ACTIVE",
            generated_by="mesh_dry_run",
            metadata={"dry_run_phase": "v2_part4b"},
        )
    )
    BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])
    DryRunProvenanceService().analyze_recent(limit=10)


def test_dashboard_dry_run_provenance_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/dry-run-provenance")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["brain_outputs_runtime"] == 0
    assert payload["brain_outputs_dry_run"] == 1
    assert payload["coordinator_decisions_runtime"] == 0
    assert payload["coordinator_decisions_dry_run"] == 1
    assert payload["paper_ready"] is False


def test_mesh_includes_dry_run_provenance_layer_and_blockers(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "dry_run_provenance" in payload["layers"]
    assert payload["layers"]["dry_run_provenance"]["mock_data"] is False
    assert payload["flow"]["dry_run_provenance"]["brain_outputs_dry_run"] == 1
    assert payload["readiness"]["paper_ready"] is False
    assert "BRAIN_OUTPUTS_DRY_RUN_ONLY" in payload["readiness"]["blocked_by"]
    assert "COORDINATOR_DECISIONS_DRY_RUN_ONLY" in payload["readiness"]["blocked_by"]
