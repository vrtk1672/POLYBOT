from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.lineage import SignalLineage
from app.repositories.signal_lineage_repository import SignalLineageRepository
from app.services.lineage_coverage import LineageCoverageService
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
        conn.execute("DELETE FROM signal_lineage_coverage_runs")
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="dashboard-lineage-signal",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:dashboard",
            correlation_id="corr-dashboard-lineage",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalLineageRepository().attach_signal_binding(
            conn,
            SignalLineage(
                signal_id=str(signal["signal_id"]),
                neuron_name="rules",
                producer_name="rules_resolution_adapter",
                source_name="rules_resolution_truth",
                source_event_id="evt-dashboard",
                correlation_id="corr-dashboard-lineage",
                raw_payload_ref="rules:dashboard",
                generated_from="rules_resolution",
                lineage={"raw_payload_policy": "reference_only"},
            ),
        )
    LineageCoverageService().analyze_recent_signals(limit=10)


def test_dashboard_lineage_coverage_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/lineage-coverage")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_analyzed"] == 1
    assert payload["bound_signals"] == 1
    assert payload["paper_ready"] is False
    assert "producer_coverage" in payload
    assert "source_coverage" in payload
    assert "raw_payload_coverage" in payload
    assert "correlation_coverage" in payload


def test_mesh_dashboard_includes_lineage_coverage_layer_and_blockers(postgres_test_schema) -> None:
    _prepare()
    NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="dashboard-lineage-unbound",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="ACTIVE",
        )
    )
    LineageCoverageService().analyze_recent_signals(limit=10)

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "lineage_coverage" in payload["layers"]
    assert payload["layers"]["lineage_coverage"]["mock_data"] is False
    assert payload["flow"]["lineage_coverage"]["unbound_signals"] >= 1
    assert payload["readiness"]["paper_ready"] is False
    assert "SIGNALS_UNBOUND_HIGH" in payload["readiness"]["blocked_by"]
