from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
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


def _clear_mesh() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM neuron_health")
        conn.execute("DELETE FROM source_status")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_dashboard_neurons_route_loads() -> None:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    paths = {route.path for route in app.routes}
    assert "/dashboard/api/v2/neurons" in paths


def test_dashboard_neurons_returns_real_summary(postgres_test_schema) -> None:
    _clear_mesh()
    NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="ACTIVE",
            market_id="market-dashboard",
            raw_direction="neutral",
        )
    )

    with _client() as client:
        response = client.get("/dashboard/api/v2/neurons")
    payload = response.json()

    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_neurons"] >= 15
    assert payload["active_neurons"] >= 1
    assert payload["signals_per_neuron"]
    assert any(item["neuron_name"] == "rules" for item in payload["last_signal_by_neuron"])


def test_dashboard_overview_keeps_signal_and_neuron_truth(postgres_test_schema) -> None:
    _clear_mesh()
    with _client() as client:
        payload = client.get("/dashboard/api/v2/overview").json()

    assert payload["data_source"]["mock_data"] is False
    assert "signals" in payload["data"]
    assert "neurons" in payload["data"]
    assert payload["data"]["summary"]["total_neurons"] >= 15
