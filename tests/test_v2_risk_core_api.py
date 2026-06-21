from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_risk_core_api_returns_mock_data_false(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    evaluated = client.post("/risk/core/evaluate", json={"limit": 10, "write_decisions": False})
    recent = client.get("/risk/decisions/recent")

    assert evaluated.status_code == 200
    assert evaluated.json()["mock_data"] is False
    assert evaluated.json()["paper_ready_after"] is False
    assert recent.status_code == 200
    assert recent.json()["mock_data"] is False

