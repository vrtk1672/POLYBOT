from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.brain_coordinator import BrainCoordinatorService
from app.services.brain_outputs import BrainOutputService
from app.services.query.dashboard_v2_query_service import DashboardV2QueryService


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
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_dashboard_coordinator_empty_truth(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        response = client.get("/dashboard/api/v2/coordinator")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_decisions_24h"] == 0
    assert payload["execution_allowed_count"] == 0


def test_dashboard_coordinator_reports_decision_counts(postgres_test_schema) -> None:
    _clear()
    output = BrainOutputService().create_brain_output(
        {"brain": "no_trade", "output_type": "NO_TRADE_HINT", "recommendation": "NO_TRADE", "status": "ACTIVE", "confidence": 0.8}
    )
    BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    with _client() as client:
        response = client.get("/dashboard/api/v2/coordinator")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_decisions_24h"] == 1
    assert payload["no_trade_decisions_24h"] == 1
    assert payload["execution_allowed_count"] == 0


def test_dashboard_v2_page_includes_coordinator(postgres_test_schema) -> None:
    _clear()
    output = BrainOutputService().create_brain_output(
        {"brain": "memory", "output_type": "MEMORY_NOTE", "recommendation": "WATCH", "status": "ACTIVE"}
    )
    BrainCoordinatorService().coordinate_outputs([str(output["brain_output_id"])])

    payload = DashboardV2QueryService().get_page("coordinator")

    assert payload["status"] == "OK"
    assert payload["data_source"]["mock_data"] is False
    assert payload["data"]["coordinator"]["total_decisions_24h"] == 1
