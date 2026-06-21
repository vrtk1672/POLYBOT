from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_eligibility import PaperEligibilityService

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain


def test_dashboard_paper_eligibility_and_mesh_layer(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("dashboard", exit_status="BLOCKED", paper_exit_ready=False, risk_approved=False)
    PaperEligibilityService().evaluate_candidates(limit=10)
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/paper-eligibility")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert payload["total_candidates"] == 1

    mesh = client.get("/dashboard/api/v2/mesh").json()
    assert "paper_eligibility" in mesh["layers"]
    assert "paper_eligibility" in mesh["flow"]
    assert "paper_eligibility_summary" in mesh["readiness"]
