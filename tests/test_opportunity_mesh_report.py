from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_defense import PaperDefenseGovernor

from opportunity_mesh_fixtures import prepare_opportunity_mesh_fixture, seed_paper_intent, seed_runtime_decision


def test_opportunity_mesh_api_and_learning_report_expose_lifecycle_summary(postgres_test_schema) -> None:
    prepare_opportunity_mesh_fixture()
    seed_runtime_decision(decision_id="decision-ready-report", market_id="market-ready-report", score=63.0)
    seed_paper_intent(
        intent_id="intent-report-stuck",
        eligibility_id="eligibility-report-stuck",
        market_id="market-report-stuck",
        seconds_old=1200,
        execution_block_reason="MISSING_TRUSTED_ORDERBOOK",
    )

    response = TestClient(app).get("/dashboard/api/v2/control/opportunity-mesh?limit=20")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["summary"]["ready_for_intent"] == 1
    assert payload["summary"]["intent_stuck"] == 1

    report = PaperDefenseGovernor().learning_report(write_files=False)
    hunting = report["hunting_summary"]
    assert "opportunity_mesh_summary" in hunting
    assert "candidate_consumption_summary" in hunting
    assert hunting["opportunity_mesh_summary"]["intent_stuck"] == 1
