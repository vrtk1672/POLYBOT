from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_evidence_refresh_truth_is_real(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    response = client.get("/dashboard/api/v2/evidence-refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert "evidence_refresh_allowed" in payload
    assert payload["evidence_refresh_active"] is False
    assert payload["paper_ready"] is False
