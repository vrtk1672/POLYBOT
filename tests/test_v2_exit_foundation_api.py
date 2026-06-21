from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_exit_foundation_api_build_and_recent(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    result = client.post("/exit/plans/build", json={"limit": 10, "include_blocked": True, "write_plans": True})
    recent = client.get("/exit/plans/recent")

    assert result.status_code == 200
    assert result.json()["mock_data"] is False
    assert result.json()["paper_ready_after"] is False
    assert result.json()["orders_created"] == 0
    assert result.json()["order_intents_created"] == 0
    assert recent.status_code == 200
    assert recent.json()["mock_data"] is False
    assert "exit_plans" in recent.json()
