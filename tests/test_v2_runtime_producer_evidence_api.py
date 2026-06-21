from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository


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
        conn.execute("DELETE FROM runtime_producer_evidence_items")
        conn.execute("DELETE FROM runtime_producer_evidence_runs")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM source_status")
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
                "notes": "runtime evidence api seed",
            },
        )


def test_runtime_evidence_endpoint_returns_mock_data_false(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.post(
            "/producers/runtime-evidence/run",
            json={"limit": 10, "producer_names": [], "dry_run": False, "apply_evaluations": True},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["signals_created"] == 1
    assert payload["paper_ready_after"] is False
    assert payload["orders_created"] == 0
    assert payload["order_intents_created"] == 0
    assert payload["live_actions_created"] == 0
