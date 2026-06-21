from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_risk_core_and_mesh_layer(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/risk-core")
    mesh = client.get("/dashboard/api/v2/mesh")

    assert dashboard.status_code == 200
    assert dashboard.json()["mock_data"] is False
    assert dashboard.json()["paper_ready"] is False
    assert "top_risk_blockers" in dashboard.json()
    assert mesh.status_code == 200
    assert "risk_core" in mesh.json()["layers"]
    assert "risk_summary" in mesh.json()["readiness"]

