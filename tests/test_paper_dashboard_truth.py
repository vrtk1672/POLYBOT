from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from test_paper_execution_service import _prepare, _seed_intent, _service


def test_unified_paper_dashboard_returns_db_backed_truth(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="dashboard-truth")
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["paper_intents_total"] == 1
    assert payload["paper_orders_total"] == 1
    assert payload["paper_fills_total"] == 1
    assert payload["paper_positions_total"] == 1
    assert payload["open_paper_positions"] == 1
    assert payload["live_orders"] == 0
    assert payload["live_enabled"] is False
    assert payload["shadow_enabled"] is False


def test_dashboard_reads_do_not_create_duplicate_paper_events(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="dashboard-idempotent")
    client = TestClient(create_app())

    first = client.get("/dashboard/api/v2/paper").json()
    second = client.get("/dashboard/api/v2/paper").json()

    assert first["paper_orders_total"] == second["paper_orders_total"] == 1
    assert first["paper_fills_total"] == second["paper_fills_total"] == 1
    assert first["paper_positions_total"] == second["paper_positions_total"] == 1
    assert second["mock_data"] is False
