from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
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


def test_dashboard_producer_health_endpoint_returns_required_fields(postgres_test_schema) -> None:
    run_migrations()

    with _client() as client:
        response = client.get("/dashboard/api/v2/producer-health")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    for key in (
        "overall_status",
        "total_producers",
        "registered_producers",
        "observed_producers",
        "runtime_active_producers",
        "dry_run_only_producers",
        "silent_expected_neurons",
        "missing_neurons",
        "degraded_neurons",
        "producer_health",
        "neuron_runtime_truth",
    ):
        assert key in payload


def test_mesh_dashboard_includes_producer_health_layer(postgres_test_schema) -> None:
    run_migrations()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "producer_health" in payload["layers"]
    assert payload["layers"]["producer_health"]["mock_data"] is False
    assert "producer_health" in payload["flow"]
    assert "producer_health_summary" in payload["readiness"]
    assert payload["readiness"]["paper_ready"] is False
