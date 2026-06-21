from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate


def test_dashboard_no_trade_and_mesh_layer(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("dashboard-no-trade")
    PaperIntentGateService().build_intents(limit=10)
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/no-trade")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["total_no_trade_records"] == 1

    mesh = client.get("/dashboard/api/v2/mesh").json()
    assert "no_trade" in mesh["layers"]
    assert "no_trade" in mesh["flow"]
    assert "no_trade_summary" in mesh["readiness"]
