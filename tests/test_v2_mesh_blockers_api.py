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
            ('BRAIN_OUTPUT', 'bo-dry-1', 'dry_run', 'dry_api', 'risk', true, false, false, false, 'DRY_RUN_ONLY', 0.95, 'test dry run', true, false, 'brain_outputs', now()),
            ('COORDINATOR_DECISION', 'coord-dry-1', 'dry_run', 'dry_api', 'coordinator', true, false, false, false, 'DRY_RUN_ONLY', 0.95, 'test dry run', true, false, 'coordinator_decisions', now())
            """
        )


def test_mesh_blockers_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh-blockers")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["overall_status"] == "BLOCKED"
    assert "BRAIN_OUTPUTS_DRY_RUN_ONLY" in payload["blocked_by"]
    assert "COORDINATOR_DECISIONS_DRY_RUN_ONLY" in payload["blocked_by"]
    assert payload["counts"]["active_blockers"] > 0


def test_mesh_blockers_endpoint_distinguishes_info_from_blockers(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh-blockers").json()

    info_codes = {item["code"] for item in payload["info"]}
    assert "LIVE_DISABLED" in info_codes
    assert "PAPER_ORDERS_ZERO" in info_codes
    assert "LIVE_DISABLED" not in payload["blocked_by"]
