from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_dashboard_paper_exit_and_pnl_truth_are_real(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    exits = client.get("/dashboard/api/v2/paper-exits")
    pnl = client.get("/dashboard/api/v2/paper-pnl")

    assert exits.status_code == 200
    assert pnl.status_code == 200
    exits_payload = exits.json()
    pnl_payload = pnl.json()
    assert exits_payload["mock_data"] is False
    assert pnl_payload["mock_data"] is False
    assert "open_paper_positions" in exits_payload
    assert "realized_pnl" in pnl_payload
    assert exits_payload["live_orders"] == 0
    assert pnl_payload["paper_ready"] is False
