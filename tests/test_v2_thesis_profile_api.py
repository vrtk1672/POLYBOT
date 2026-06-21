from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_thesis_profile_api_returns_mock_data_false(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    build = client.post("/thesis/profiles/build", json={"limit": 10, "write_profiles": False})
    recent = client.get("/thesis/profiles/recent")

    assert build.status_code == 200
    assert build.json()["mock_data"] is False
    assert build.json()["paper_ready_after"] is False
    assert recent.status_code == 200
    assert recent.json()["mock_data"] is False

