from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_thesis_profile_foundation_and_mesh_layer(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/thesis")
    mesh = client.get("/dashboard/api/v2/mesh")

    assert dashboard.status_code == 200
    assert dashboard.json()["mock_data"] is False
    assert dashboard.json()["paper_ready"] is False
    assert "missing_evidence_summary" in dashboard.json()
    assert mesh.status_code == 200
    assert "thesis_profiles" in mesh.json()["layers"]
    assert "thesis_summary" in mesh.json()["readiness"]

