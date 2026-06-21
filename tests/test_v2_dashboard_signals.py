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


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_dashboard_v2_signals_route_loads() -> None:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    paths = {route.path for route in app.routes}
    assert "/dashboard/api/v2/signals" in paths


def test_dashboard_signals_empty_db_returns_truth_envelope(postgres_test_schema) -> None:
    _clear()
    with _client() as client:
        response = client.get("/dashboard/api/v2/signals")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"]["mock_data"] is False
    assert payload["data"]["signals"]["total_signals_24h"] == 0
    assert payload["data"]["signals"]["latest_signals"] == []
    assert payload["data"]["signals"]["unprocessed_signals"] == 0


def test_dashboard_signals_reports_counts(postgres_test_schema) -> None:
    _clear()
    NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="orderbook",
            event_type="source_status_observed",
            source_name="polymarket_clob_orderbook",
            market_id="market-dash",
            status="ACTIVE",
            raw_direction="neutral",
        )
    )

    with _client() as client:
        payload = client.get("/dashboard/api/v2/signals").json()

    signals = payload["data"]["signals"]
    assert payload["data_source"]["mock_data"] is False
    assert signals["signal_status"] == "OK"
    assert signals["total_signals_24h"] == 1
    assert signals["unprocessed_signals"] == 1
    assert signals["signals_by_neuron"][0]["neuron"] == "orderbook"
