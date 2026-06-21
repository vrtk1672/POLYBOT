from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

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


def test_dashboard_v2_routes_load() -> None:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    paths = {route.path for route in app.routes}
    expected = {
        "/dashboard/api/v2/overview",
        "/dashboard/api/v2/source-status",
        "/dashboard/api/v2/rules",
        "/dashboard/api/v2/events",
        "/dashboard/api/v2/risk",
        "/dashboard/api/v2/engines",
        "/dashboard/api/v2/ai",
        "/dashboard/api/v2/no-trade",
        "/dashboard/api/v2/learning",
        "/dashboard/api/v2/memory",
        "/dashboard/api/v2/market",
        "/dashboard/api/v2/opportunities",
        "/dashboard/api/v2/capital",
        "/dashboard/api/v2/execution",
        "/dashboard/api/v2/exits",
        "/dashboard/api/v2/news",
        "/dashboard/api/v2/social",
        "/dashboard/api/v2/whales",
        "/dashboard/api/v2/live-flow",
        "/dashboard/api/v2/settings",
    }
    assert expected <= paths


def test_dashboard_v2_endpoints_return_truth_envelope(postgres_test_schema) -> None:
    with _client() as client:
        for path in (
            "/dashboard/api/v2/overview",
            "/dashboard/api/v2/events",
            "/dashboard/api/v2/risk",
            "/dashboard/api/v2/engines",
            "/dashboard/api/v2/ai",
            "/dashboard/api/v2/no-trade",
            "/dashboard/api/v2/learning",
            "/dashboard/api/v2/memory",
            "/dashboard/api/v2/market",
            "/dashboard/api/v2/opportunities",
            "/dashboard/api/v2/capital",
            "/dashboard/api/v2/execution",
            "/dashboard/api/v2/exits",
            "/dashboard/api/v2/news",
            "/dashboard/api/v2/social",
            "/dashboard/api/v2/whales",
            "/dashboard/api/v2/live-flow",
            "/dashboard/api/v2/settings",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            payload = response.json()
            assert {"status", "updated_at", "stale", "stale_reason", "data_source", "data_confidence", "errors", "data"} <= set(payload)
            assert payload["data_source"]["mock_data"] is False
            assert payload["data_source"]["type"] == "postgres_runtime_truth"
            assert 0 <= payload["data_confidence"] <= 1


def test_dashboard_v2_missing_data_is_explicit(postgres_test_schema) -> None:
    with _client() as client:
        payload = client.get("/dashboard/api/v2/ai").json()
    assert payload["stale"] is True
    assert payload["stale_reason"]
    assert payload["status"] in {"STALE", "NO_DATA", "DEGRADED", "ERROR"}
    assert payload["data_confidence"] <= 0.55


def test_dashboard_v2_html_contains_locked_advanced_control() -> None:
    with _client() as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert "POLYBOT Operator Control Room" in response.text
    assert "Advanced Control" in response.text
    assert "Reason required" in response.text
    assert "Control unavailable from Dashboard V2" in response.text
    assert "/dashboard/api/v2/" in response.text


def test_dashboard_v2_api_does_not_mutate_order_tables(postgres_test_schema) -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "orders_v2": conn.execute("SELECT COUNT(*) AS count FROM orders_v2").fetchone()["count"],
            "exit_intents": conn.execute("SELECT COUNT(*) AS count FROM exit_intents").fetchone()["count"],
        }

    with _client() as client:
        assert client.get("/dashboard/api/v2/overview").status_code == 200
        assert client.get("/dashboard/api/v2/execution").status_code == 200
        assert client.get("/dashboard/api/v2/exits").status_code == 200
        assert client.get("/dashboard/api/v2/settings").status_code == 200

    with factory.connect() as conn:
        after = {
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "orders_v2": conn.execute("SELECT COUNT(*) AS count FROM orders_v2").fetchone()["count"],
            "exit_intents": conn.execute("SELECT COUNT(*) AS count FROM exit_intents").fetchone()["count"],
        }

    assert before == after
