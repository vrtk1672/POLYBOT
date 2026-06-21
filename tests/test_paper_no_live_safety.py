from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from test_paper_execution_service import _prepare, _seed_intent, _service


def test_paper_dashboard_reports_no_live_or_real_mutation(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="no-live")
    client = TestClient(create_app())

    payload = client.get("/dashboard/api/v2/paper").json()

    assert payload["mock_data"] is False
    assert payload["live_orders"] == 0
    assert payload["live_enabled"] is False
    assert payload["shadow_enabled"] is False
    assert payload["orders_v2"] == payload["real_orders_current"]
    assert payload["fills_v2"] == 0
    assert payload["canonical_positions"] == 0
    assert payload["no_fake_pnl"] is True
