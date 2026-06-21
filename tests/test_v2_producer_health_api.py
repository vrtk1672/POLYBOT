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


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM dry_run_provenance_analysis")
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, status, raw_direction,
                confidence, strength, evidence_json, raw_payload_ref, processed_by_brain,
                created_at
            )
            VALUES (
                'producer-api-sig-1', 'market', 'source_status_observed', 'runtime_api_source',
                'ACTIVE', 'neutral', 0.8, 0.7, '{}'::jsonb, 'payload://producer-api',
                false, now()
            )
            """
        )
        conn.execute(
            """
            INSERT INTO neuron_signal_bindings (
                signal_id, neuron_name, producer_name, producer_component, source_name,
                correlation_id, raw_payload_ref, generated_from, lineage_json
            )
            VALUES (
                'producer-api-sig-1', 'market', 'runtime_api_adapter',
                'tests', 'runtime_api_source', 'corr-producer-api',
                'payload://producer-api', 'event_log', '{}'::jsonb
            )
            """
        )


def test_producer_health_endpoint_returns_truth(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        response = client.get("/dashboard/api/v2/producer-health")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["total_producers"] >= 1
    assert payload["producer_health"]
    assert "neuron_runtime_truth" in payload


def test_producer_health_endpoint_reports_runtime_adapter(postgres_test_schema) -> None:
    _prepare()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/producer-health").json()

    names = {item["producer_name"] for item in payload["producer_health"]}
    assert "runtime_api_adapter" in names
    item = next(item for item in payload["producer_health"] if item["producer_name"] == "runtime_api_adapter")
    assert item["observed"] is True
    assert item["runtime_signal_count"] == 1
