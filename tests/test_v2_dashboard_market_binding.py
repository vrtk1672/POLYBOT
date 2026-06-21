from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_market_binding_and_mesh_layer(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    dashboard = client.get("/dashboard/api/v2/market-binding")
    mesh = client.get("/dashboard/api/v2/mesh")

    assert dashboard.status_code == 200
    assert dashboard.json()["mock_data"] is False
    assert dashboard.json()["paper_ready"] is False
    assert mesh.status_code == 200
    assert "market_binding" in mesh.json()["layers"]
    assert "market_binding" in mesh.json()["flow"]

