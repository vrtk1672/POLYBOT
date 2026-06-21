from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_market_binding_api_returns_mock_data_false(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    response = client.post("/signals/market-binding/recover", json={"limit": 10, "apply_safe_links": False})

    assert response.status_code == 200
    assert response.json()["mock_data"] is False

