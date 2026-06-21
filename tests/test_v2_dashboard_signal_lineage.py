from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
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


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_dashboard_signal_lineage_endpoint_returns_truth(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().create_signal({"neuron": "market", "event_type": "source_status_observed", "status": "ACTIVE"})
    NeuronSignalService().create_signal_with_lineage(
        {"neuron": "rules", "event_type": "rules_resolution_status_observed", "status": "ACTIVE", "correlation_id": "corr-dash"},
        {"producer_name": "rules_resolution_adapter", "generated_from": "rules_resolution", "correlation_id": "corr-dash"},
    )
    with _client() as client:
        response = client.get("/dashboard/api/v2/signal-lineage")
    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_signals_24h"] == 2
    assert payload["bound_signals_24h"] == 1
    assert payload["unbound_signals_24h"] == 1


def test_dashboard_signals_includes_lineage_summary(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        payload = client.get("/dashboard/api/v2/signals").json()
    assert payload["data_source"]["mock_data"] is False
    assert "signal_lineage" in payload["data"]
