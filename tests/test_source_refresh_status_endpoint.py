from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.source_refresh_orchestrator import SourceRefreshOrchestrator


def test_source_refresh_status_endpoint_exposes_contract_shape(postgres_test_schema) -> None:
    run_migrations()
    _clean_tables()
    _insert_status_row()
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/source-refresh-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "REAL"
    assert payload["source_refresh_orchestrator_state"] in {"ACTIVE", "NOT_STARTED"}
    assert "per_source" in payload
    assert payload["per_source"][0]["source_name"] == "orderbook_signals"
    assert payload["per_source"][0]["refresh_state"] == "FRESH"
    assert "missing_config_sources" in payload


def test_source_refresh_status_endpoint_bootstraps_when_tables_missing(postgres_test_schema) -> None:
    run_migrations()
    _clean_tables()

    payload = SourceRefreshOrchestrator().status()

    assert payload["status"] in {"REAL", "MISSING"}
    assert "per_source" in payload
    assert any(item["source_name"] == "payout" for item in payload["per_source"])


def _clean_tables() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("source_refresh_status", "source_refresh_cycles"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _insert_status_row() -> None:
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SourceRefreshOrchestrator()._ensure_tables(conn)
        conn.execute(
            """
            INSERT INTO source_refresh_status (
                source_name, source_type, enabled, refresh_mode, candidate_scoped_supported,
                market_level_supported, directional_supported, last_refresh_attempt_at,
                last_successful_refresh_at, latest_data_at, refresh_interval_seconds,
                ttl_seconds, freshness_seconds, refresh_state, rows_total, rows_last_24h,
                rows_last_1h, rows_last_15m, candidate_linked_rows, directional_rows,
                safe_to_refresh_data_only, required_config_keys, missing_config_keys,
                required_to_pass, metadata_json
            )
            VALUES (
                'orderbook_signals', 'ORDERBOOK_SIGNAL', true, 'DERIVED', true,
                true, true, %s, %s, %s, 300, 900, 20, 'FRESH',
                1, 1, 1, 1, 1, 1, true, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb
            )
            """,
            (now, now, now),
        )


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}
