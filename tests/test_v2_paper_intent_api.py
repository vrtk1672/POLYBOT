from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate


def test_paper_intent_api_build_and_recent(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("api")
    client = TestClient(app)

    built = client.post("/paper/intents/build", json={"limit": 10, "write_intents": True, "write_no_trade": True})
    assert built.status_code == 200
    payload = built.json()
    assert payload["mock_data"] is False
    assert payload["paper_ready_after"] is False
    assert payload["no_trade_records_created"] == 1

    recent = client.get("/paper/intents/recent")
    assert recent.status_code == 200
    assert recent.json()["mock_data"] is False
    assert recent.json()["count"] == 0
