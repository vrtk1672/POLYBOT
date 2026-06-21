from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from test_paper_execution_service import _prepare, _seed_intent, _service


def test_valid_paper_execution_has_no_orphans_or_duplicates(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="no-orphans")
    client = TestClient(create_app())

    payload = client.get("/dashboard/api/v2/paper").json()

    assert payload["orphan_positions_count"] == 0
    assert payload["duplicate_orders_count"] == 0
    assert payload["duplicate_fills_count"] == 0
    assert payload["duplicate_positions_count"] == 0


def test_positions_endpoint_exposes_full_lineage_fields(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    _service().run_execution(correlation_id="positions-lineage")
    client = TestClient(create_app())

    payload = client.get("/dashboard/api/v2/paper/positions").json()

    assert payload["mock_data"] is False
    assert payload["count"] == 1
    position = payload["positions"][0]
    assert position["paper_intent_id"]
    assert position["paper_order_id"]
    assert position["paper_fill_id"]
    assert position["risk_decision_id"] == "risk-test"
    assert position["exit_plan_id"] == "exit-test"
    assert position["eligibility_id"].startswith("eligibility-")
