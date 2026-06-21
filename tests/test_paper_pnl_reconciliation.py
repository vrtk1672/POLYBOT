from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from test_paper_exit_loop import _lock_position, _prepare, _seed_position, _service


def test_unified_pnl_reconciles_realized_daily_truth(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)
    _service().run_exit_loop(correlation_id="pnl-reconcile")
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper/pnl")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["reconciliation_status"] == "OK"
    assert payload["realized_pnl"] == 1.0
    assert payload["gross_profit"] == 1.0
    assert payload["closed_trades"] == 1
    assert payload["pnl_source"] == "paper_daily_pnl"


def test_unified_pnl_does_not_fake_profit_without_closes(postgres_test_schema) -> None:
    _prepare()
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/paper/pnl")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["realized_pnl"] == 0.0
    assert payload["closed_trades"] == 0
