from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

from test_paper_execution_service import _prepare, _seed_intent, _service


def test_dashboard_returns_real_paper_execution_truth(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="dashboard")
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper-execution")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["paper_orders"] == 1
    assert payload["paper_fills"] == 1
    assert payload["paper_positions"] == 1
    assert payload["open_paper_positions"] == 1
    assert payload["no_live_execution"] is True
    assert payload["paper_exit_loop_ready"] is True
    assert payload["pnl_ready"] is True
