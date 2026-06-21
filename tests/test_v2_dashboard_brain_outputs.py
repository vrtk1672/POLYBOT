from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.services.brain_outputs import BrainOutputService
from app.services.query.dashboard_v2_query_service import DashboardV2QueryService


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_router())
    return TestClient(app)


def test_dashboard_brain_outputs_endpoint_returns_truth_when_empty(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        response = client.get("/dashboard/api/v2/brain-outputs")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_outputs_24h"] == 0
    assert payload["latest_outputs"] == []


def test_dashboard_brain_outputs_endpoint_returns_counts(postgres_test_schema) -> None:
    _clear()
    BrainOutputService().create_brain_output(
        {"brain": "context", "output_type": "WATCH", "recommendation": "WATCH", "status": "ACTIVE"}
    )

    with _client() as client:
        response = client.get("/dashboard/api/v2/brain-outputs")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["total_outputs_24h"] == 1
    assert payload["outputs_by_brain"][0]["brain"] == "context"


def test_dashboard_v2_page_includes_brain_outputs(postgres_test_schema) -> None:
    _clear()
    BrainOutputService().create_brain_output(
        {"brain": "memory", "output_type": "MEMORY_NOTE", "recommendation": "WATCH", "status": "ACTIVE"}
    )

    payload = DashboardV2QueryService().get_page("brain-outputs")

    assert payload["status"] == "OK"
    assert payload["data_source"]["mock_data"] is False
    assert payload["data"]["brain_outputs"]["total_outputs_24h"] == 1
