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


def test_dashboard_orderbook_and_mesh_include_orderbook_layer(postgres_test_schema) -> None:
    run_migrations()
    with _client() as client:
        orderbook = client.get("/dashboard/api/v2/orderbook").json()
        mesh = client.get("/dashboard/api/v2/mesh").json()

    assert orderbook["mock_data"] is False
    assert orderbook["paper_ready"] is False
    assert "total_snapshots" in orderbook
    assert mesh["mock_data"] is False
    assert "orderbook" in mesh["layers"]
    assert "orderbook" in mesh["flow"]
    assert "orderbook_summary" in mesh["readiness"]
