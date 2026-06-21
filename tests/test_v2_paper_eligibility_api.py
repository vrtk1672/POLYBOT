from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

from paper_eligibility_fixtures import prepare_paper_eligibility_schema, seed_paper_eligibility_chain


def test_paper_eligibility_api_evaluate_and_recent(postgres_test_schema) -> None:
    prepare_paper_eligibility_schema()
    seed_paper_eligibility_chain("api", exit_status="BLOCKED", paper_exit_ready=False, risk_approved=False)
    client = TestClient(app)

    evaluated = client.post("/paper/eligibility/evaluate", json={"limit": 10, "include_blocked": True, "write_candidates": True})
    assert evaluated.status_code == 200
    assert evaluated.json()["mock_data"] is False
    assert evaluated.json()["paper_ready_after"] is False

    recent = client.get("/paper/eligibility/recent")
    assert recent.status_code == 200
    assert recent.json()["count"] == 1
    assert recent.json()["candidates"][0]["paper_intent_allowed"] is False
