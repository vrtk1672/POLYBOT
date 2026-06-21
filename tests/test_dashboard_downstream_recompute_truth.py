from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_downstream_recompute_truth_is_real(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    response = client.get("/dashboard/api/v2/downstream-recompute")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert "downstream_recompute_allowed" in payload
    assert payload["downstream_recompute_active"] is False
    assert payload["paper_ready"] is False
