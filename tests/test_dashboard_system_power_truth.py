from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app
from app.services.system_power import SystemPowerService


def test_dashboard_system_power_truth(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_off(actor="operator", reason="dashboard_truth_test", correlation_id="dashboard-power")
    client = TestClient(app)

    response = client.get("/dashboard/api/v2/system-power")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["system_power"] == "OFF"
    assert payload["runtime_work_allowed"] is False
    assert payload["scheduler_allowed"] is False
    assert payload["market_service_allowed"] is False
    assert payload["data_intake_allowed"] is False
    assert payload["paper_allowed"] is False
    assert payload["shadow_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["safety"]["orders_allowed"] is False
    assert payload["components"]["brain_dialogue_feed"]["wired"] is True
