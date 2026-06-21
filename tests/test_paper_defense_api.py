from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_paper_defense_endpoint_returns_policy_summary() -> None:
    response = TestClient(app).get("/dashboard/api/v2/control/paper-defense")
    assert response.status_code == 200
    payload = response.json()
    assert "defense_level" in payload
    assert "blocker_policy_summary" in payload
    assert payload["blocker_policy_summary"]["integrity_never_ignore"]


def test_learning_report_endpoint_is_available() -> None:
    response = TestClient(app).get("/dashboard/api/v2/control/paper-session/learning-report")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"OK", "NO_ACTIVE_PAPER_SESSION", "DATABASE_UNAVAILABLE"}
