from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.learning_routes import create_learning_router
from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from test_v2_19_fixtures import completed_trade_payload


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_learning_router())
    return TestClient(app)


def test_learning_routes_load():
    app = FastAPI()
    app.include_router(create_learning_router())
    paths = {route.path for route in app.routes}
    assert {
        "/learning/health",
        "/learning/trade-reviews/recent",
        "/learning/signals",
        "/learning/engines",
        "/learning/sources",
        "/learning/whales",
        "/learning/ai",
        "/learning/no-trade",
        "/learning/model-adjustments",
        "/learning/snapshot",
        "/learning/review/trade",
        "/learning/review/no-trade",
        "/learning/rebuild",
    } <= paths


def test_learning_api_persists_review_only(postgres_test_schema):
    run_migrations()
    with _client() as client:
        response = client.post("/learning/review/trade", json={"dry_run": False, "manual_completed_trade": completed_trade_payload()})
    assert response.status_code == 200
    assert response.json()["written"] is True
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM trade_reviews").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"] == 0
        assert conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"] == 0


def test_learning_api_dry_run_writes_nothing(postgres_test_schema):
    run_migrations()
    with _client() as client:
        response = client.post("/learning/review/trade", json={"dry_run": True, "manual_completed_trade": completed_trade_payload()})
    assert response.status_code == 200
    assert response.json()["written"] is False
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM trade_reviews").fetchone()["count"] == 0


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit=None):
        return []

    async def raw_counts(self):
        return {"raw_market_count": 0}

    async def last_refresh(self):
        return {"last_refresh_at": None}


def test_dashboard_v2_learning_route_loads(postgres_test_schema):
    run_migrations()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    with TestClient(app) as client:
        response = client.get("/dashboard/api/v2/learning")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"]["mock_data"] is False
    assert payload["data_source"]["type"] == "postgres_runtime_truth"
