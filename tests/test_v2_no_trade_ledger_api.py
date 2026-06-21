from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.paper_intents import PaperIntentGateService

from paper_intent_fixtures import prepare_paper_intent_schema, seed_blocked_candidate


def test_no_trade_recent_api_returns_ledger_records(postgres_test_schema) -> None:
    prepare_paper_intent_schema()
    seed_blocked_candidate("api-ledger")
    PaperIntentGateService().build_intents(limit=10)
    client = TestClient(app)

    response = client.get("/no-trade/recent")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_data"] is False
    assert payload["count"] == 1
    assert payload["no_trade_records"][0]["blockers"]
