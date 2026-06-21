from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_eligible_candidate


def test_dashboard_paper_intents_and_mesh_layer(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_eligible_candidate("dashboard-intent")
    PaperIntentGateService().build_intents(limit=10)
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/paper-intents")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["total_paper_intents"] == 1

    mesh = client.get("/dashboard/api/v2/mesh").json()
    assert "paper_intents" in mesh["layers"]
    assert "paper_intents" in mesh["flow"]
    assert "paper_intent_summary" in mesh["readiness"]
