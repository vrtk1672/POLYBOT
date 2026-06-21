from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from test_paper_execution_service import _prepare, _seed_intent, _service


def test_soak_readiness_endpoint_is_real_and_safety_backed(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="soak-readiness")
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper/soak-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["safety_status"] == "GREEN"
    assert payload["preflight_counts"]["paper_orders_total"] == 1
    assert payload["preflight_counts"]["paper_fills_total"] == 1
    assert payload["preflight_counts"]["paper_positions_total"] == 1
    assert payload["preflight_counts"]["live_orders"] == 0
    assert isinstance(payload["can_start_4h_soak"], bool)
