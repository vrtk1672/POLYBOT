from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.brain_dialogue import BrainDialogueService
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService

from test_trusted_orderbook_evidence_service import _prepare, _seed_candidate


def test_dashboard_trusted_orderbook_returns_runtime_truth(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("dashboard")
    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-dashboard", limit=10)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/trusted-orderbook?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["latest_run_status"] == "OK"
    assert payload["trusted_orderbook_matches"] == 1
    assert payload["sample_trusted_links"]
    assert payload["live_orders"] == 0


def test_dashboard_orderbook_blockers_returns_breakdown(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("blockers", insert_orderbook=False)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/orderbook-blockers?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["total_blocked"] >= 1
    assert payload["missing_fresh_orderbook_count"] >= 1
    assert "top_markets" in payload
    assert "sample_traces" in payload
    assert payload["safety_counts"]["live_orders"] == 0


def test_brain_dialogue_materializes_trusted_orderbook_link(postgres_test_schema) -> None:
    _prepare()
    _seed_candidate("dialogue")
    TrustedOrderbookEvidenceService().resolve(cycle_id="trusted-dialogue", limit=10)
    BrainDialogueService().materialize_recent(limit_per_source=20)
    client = TestClient(create_app())

    response = client.get("/dashboard/api/v2/brain-dialogue?component=Orderbook%20Neuron&limit=20")

    assert response.status_code == 200
    payload = response.json()
    messages = [event["human_message"] for event in payload["events"]]
    assert any("linked trusted orderbook" in message for message in messages)
    assert all(event["source_table"] for event in payload["events"])
