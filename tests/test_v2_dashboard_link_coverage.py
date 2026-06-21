from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.link_coverage import LinkCoverageService
from app.services.neuron_signals import NeuronSignalService


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
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="dashboard-link-unlinked",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:dashboard",
        )
    )
    LinkCoverageService().analyze_recent_signals(limit=10, create_suggestions=True, apply_safe_links=False)


def test_dashboard_link_coverage_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/link-coverage")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_analyzed"] == 1
    assert payload["unlinked_signals"] == 1
    assert payload["paper_ready"] is False
    assert "coverage_pct" in payload
    assert payload["coverage_pct"] == 0.0
    assert "link_coverage_ratio" in payload
    assert isinstance(payload["unlinked_by_reason"], list)
    assert "linkable_signals" in payload
    assert "non_linkable_signals" in payload


def test_mesh_dashboard_includes_link_coverage_layer_and_blockers(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "link_coverage" in payload["layers"]
    assert payload["layers"]["link_coverage"]["mock_data"] is False
    assert payload["flow"]["link_coverage"]["unlinked_signals"] == 1
    assert payload["readiness"]["paper_ready"] is False
    assert "SIGNALS_UNLINKED_HIGH" in payload["readiness"]["blocked_by"]
