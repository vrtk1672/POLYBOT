from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.signal_quality import SignalQualityEvaluation
from app.repositories.signal_quality_repository import SignalQualityRepository
from app.services.neuron_signals import NeuronSignalService
from app.services.signal_processing import SignalProcessingService


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
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM signal_processing_states")
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
            market_id="dashboard-processing-market",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution": "clear"},
        )
    )
    evaluation = SignalQualityEvaluation(
        signal_id=str(signal["signal_id"]),
        quality_score=0.61,
        quality_status="PARTIAL",
        missing_fields=["linked_to_position"],
        readiness_reason="brain eligible only",
        can_feed_brain=True,
        can_feed_paper=False,
        has_market_id=True,
        has_source=True,
        has_lineage=True,
        has_confidence=True,
        has_strength=True,
        has_freshness=True,
        has_evidence=True,
        linked_to_market=True,
        is_runtime_generated=True,
    )
    with factory.connect() as conn, conn.transaction():
        SignalQualityRepository().upsert_evaluation(conn, evaluation)
    SignalProcessingService().evaluate_signal_processing(str(signal["signal_id"]))
    return signal


def test_dashboard_signal_processing_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/signal-processing")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total"] == 1
    assert payload["brain_eligible_count"] == 1
    assert payload["paper_ready"] is False


def test_mesh_dashboard_includes_signal_processing_layer_and_blockers(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert "signal_processing" in payload["layers"]
    assert payload["layers"]["signal_processing"]["mock_data"] is False
    assert payload["flow"]["signal_processing"]["brain_eligible_count"] == 1
    assert payload["readiness"]["paper_ready"] is False
    assert "SIGNAL_QUALITY_GATE_BLOCKED" in payload["readiness"]["blocked_by"]


def test_signal_processing_dashboard_does_not_mutate_order_tables(postgres_test_schema) -> None:
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
        client.get("/dashboard/api/v2/signal-processing")
        client.get("/dashboard/api/v2/mesh")

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
            "execution_allowed": conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"],
        }
    assert after == before
