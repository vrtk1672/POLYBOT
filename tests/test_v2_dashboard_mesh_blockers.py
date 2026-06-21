from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


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
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute(
            """
            INSERT INTO dry_run_provenance_analysis (
                object_type, object_id, generated_by, dry_run_id, producer_name,
                is_dry_run_generated, is_runtime_generated, is_adapter_generated,
                is_manual_generated, provenance_status, provenance_confidence,
                provenance_reason, can_feed_brain_by_provenance,
                can_feed_paper_by_provenance, source_table, analyzed_at
            )
            VALUES
            ('BRAIN_OUTPUT', 'bo-mesh-dry-1', 'dry_run', 'dry_mesh', 'risk', true, false, false, false, 'DRY_RUN_ONLY', 0.95, 'test dry run', true, false, 'brain_outputs', now()),
            ('COORDINATOR_DECISION', 'coord-mesh-dry-1', 'dry_run', 'dry_mesh', 'coordinator', true, false, false, false, 'DRY_RUN_ONLY', 0.95, 'test dry run', true, false, 'coordinator_decisions', now())
            """
        )


def test_mesh_dashboard_includes_mesh_blockers_layer(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "mesh_blockers" in payload["layers"]
    assert payload["layers"]["mesh_blockers"]["mock_data"] is False
    assert payload["layers"]["mesh_blockers"]["paper_ready"] is False
    assert "BRAIN_OUTPUTS_DRY_RUN_ONLY" in payload["readiness"]["blocked_by"]
    assert "mesh_blockers" in payload["flow"]


def test_mesh_readiness_exposes_blocker_counts_and_top_blockers(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    assert payload["readiness"]["paper_ready"] is False
    assert payload["readiness"]["overall_status"] == "BLOCKED"
    assert payload["readiness"]["blocker_counts"]["active_blockers"] > 0
    assert payload["readiness"]["top_blockers"]
    assert payload["flow"]["mesh_blockers"]["blocker_counts"]["active_blockers"] > 0
