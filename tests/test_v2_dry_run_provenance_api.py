from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dry_run_provenance_routes import create_dry_run_provenance_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.brain_outputs import BrainOutput
from app.services.brain_outputs import BrainOutputService
from app.services.dry_run_provenance import DryRunProvenanceService


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_dry_run_provenance_router())
    return TestClient(app)


def _prepare() -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM dry_run_provenance_runs")
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
    return BrainOutputService().create_brain_output(
        BrainOutput(
            brain_output_id="api-provenance-bo",
            brain="risk",
            output_type="RISK_WARNING",
            recommendation="NO_TRADE_HINT",
            status="ACTIVE",
            generated_by="mesh_dry_run",
            metadata={"dry_run_phase": "v2_part4b"},
        )
    )


def test_post_analyze_recent_and_get_recent_provenance(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        analyzed = client.post("/provenance/dry-run/analyze/recent", json={"limit": 100}).json()
        recent = client.get("/provenance/dry-run/recent").json()

    assert analyzed["mock_data"] is False
    assert analyzed["summary"]["brain_outputs_dry_run"] == 1
    assert recent["mock_data"] is False
    assert recent["count"] == 1


def test_get_one_provenance(postgres_test_schema) -> None:
    output = _prepare()
    DryRunProvenanceService().analyze_recent(limit=10)

    with _client() as client:
        response = client.get(f"/provenance/dry-run/BRAIN_OUTPUT/{output['brain_output_id']}")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["provenance"]["provenance_status"] == "DRY_RUN_ONLY"
