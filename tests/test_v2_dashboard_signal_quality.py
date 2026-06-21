from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_quality import SignalQualityService


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


def _prepare() -> dict[str, object]:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="dashboard-quality-market",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution": "clear"},
        )
    )
    SignalQualityService().evaluate_signal_quality(str(signal["signal_id"]))
    return signal


def test_dashboard_signal_quality_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/signal-quality")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_evaluated"] == 1
    assert "quality_by_status" in payload
    assert "paper_blocking_reasons" in payload


def test_mesh_dashboard_includes_signal_quality_summary(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "signal_quality" in payload["layers"]
    assert payload["layers"]["signal_quality"]["mock_data"] is False
    assert payload["flow"]["signal_quality"]["can_feed_paper"] == 0
    assert payload["readiness"]["paper_ready"] is False


def test_signal_quality_dashboard_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _prepare()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "execution_allowed": conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"],
        }

    with _client() as client:
        client.get("/dashboard/api/v2/signal-quality")
        client.get("/dashboard/api/v2/mesh")

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "execution_allowed": conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"],
        }
    assert after == before
