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


def _seed_snapshot() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, depth_1c, depth_2c, depth_5c,
                bid_depth_json, ask_depth_json, raw_orderbook_json, metadata_json,
                depth_bid_1c, depth_ask_1c, depth_bid_2c, depth_ask_2c,
                total_bid_depth, total_ask_depth, liquidity_score, source,
                snapshot_status, is_stale, collected_at
            )
            VALUES (
                'ob_api_1', 'm1', 't1', 'YES', 0.49, 0.51,
                0.02, 0.50, 350, 450, 750,
                '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
                200, 150, 200, 150, 200, 150, 0.7, 'test',
                'OK', false, now()
            )
            """
        )


def test_recent_endpoint_returns_mock_data_false(postgres_test_schema) -> None:
    run_migrations()
    _seed_snapshot()

    with _client() as client:
        response = client.get("/orderbook/snapshots/recent")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["count"] == 1
    assert payload["items"][0]["market_id"] == "m1"
