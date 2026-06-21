from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import run_migrations
from app.main import app


def test_paper_capital_dashboard_returns_real_truth(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    response = client.get("/dashboard/api/v2/paper/capital")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["account_id"] == "paper_default"
    assert payload["currency"] == "USD"
    assert payload["initial_balance"] == 1000.0
    assert payload["capital_reconciliation_status"] == "OK"
    assert payload["expected_locked_balance"] == 0.0
    assert payload["actual_locked_balance"] == 0.0
    assert payload["expected_open_exposure"] == 0.0
    assert payload["actual_open_exposure"] == 0.0
    assert payload["open_positions_without_lock"] == []
    assert payload["locks_without_open_position"] == []
    assert payload["duplicate_releases"] == []
    assert payload["realized_pnl_double_apply_count"] == 0
    assert payload["live_orders"] == 0


def test_unified_paper_dashboard_includes_capital_summary(postgres_test_schema) -> None:
    run_migrations()
    client = TestClient(app)

    payload = client.get("/dashboard/api/v2/paper").json()

    assert payload["mock_data"] is False
    assert payload["capital_summary"]["account_id"] == "paper_default"
    assert payload["capital_reconciliation_status"] == "OK"
    assert payload["expected_locked_balance"] == 0.0
    assert payload["actual_open_exposure"] == 0.0
