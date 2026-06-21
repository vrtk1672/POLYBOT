from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


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


def _prepare_with_run() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "runtime_coordinator_decision_inputs",
            "runtime_coordinator_runs",
            "runtime_brain_output_inputs",
            "runtime_brain_producer_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_output_conflicts",
            "brain_outputs",
            "neuron_signal_bindings",
            "neuron_signals",
            "source_status",
        ):
            exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
            if exists:
                conn.execute(f"DELETE FROM {table}")
        SourceStatusRepository().upsert_status(
            conn,
            {
                "source_name": "polymarket_gamma",
                "source_type": "market_discovery",
                "configured": True,
                "key_required": False,
                "key_present": False,
                "key_name": None,
                "endpoint_url": "local://source-status/polymarket_gamma",
                "runtime_status": "ACTIVE",
                "freshness_status": "FRESH",
                "read_only": True,
                "mutation_allowed": False,
                "details_json": {},
                "latency_ms": 1,
                "notes": "runtime coordinator dashboard seed",
            },
        )
    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)
    RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)
    RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)


def test_dashboard_runtime_coordinator_endpoint(postgres_test_schema) -> None:
    _prepare_with_run()

    with _client() as client:
        response = client.get("/dashboard/api/v2/runtime-coordinator")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["runtime_coordinator_decisions"] == 1
    assert payload["dry_run_coordinator_decisions"] == 0
    assert payload["runtime_coordinator_decisions_created_last_run"] == 1


def test_mesh_dashboard_includes_runtime_coordinator_layer(postgres_test_schema) -> None:
    _prepare_with_run()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "runtime_coordinator" in payload["layers"]
    assert "runtime_coordinator" in payload["flow"]
    assert payload["layers"]["runtime_coordinator"]["runtime_coordinator_decisions"] == 1
    assert payload["readiness"]["runtime_coordinator_summary"]["paper_ready"] is False
