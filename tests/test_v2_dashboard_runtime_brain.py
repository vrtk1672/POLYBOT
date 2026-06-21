from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
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
            "runtime_brain_output_inputs",
            "runtime_brain_producer_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
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
                "notes": "runtime brain dashboard seed",
            },
        )
    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)
    RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)


def test_dashboard_runtime_brain_endpoint(postgres_test_schema) -> None:
    _prepare_with_run()

    with _client() as client:
        response = client.get("/dashboard/api/v2/runtime-brain")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["latest_run"] is not None
    assert payload["runtime_brain_outputs_created_last_run"] == 1
    assert payload["runtime_brain_outputs"] == 1
    assert payload["paper_ready"] is False
    assert payload["orders_created"] == 0


def test_mesh_dashboard_includes_runtime_brain_layer(postgres_test_schema) -> None:
    _prepare_with_run()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "runtime_brain" in payload["layers"]
    assert "runtime_brain" in payload["flow"]
    assert "runtime_brain_summary" in payload["readiness"]
    assert payload["readiness"]["paper_ready"] is False
