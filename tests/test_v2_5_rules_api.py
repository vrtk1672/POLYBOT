from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rules_routes import create_rules_router
from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema) -> TestClient:
    run_migrations()
    app = FastAPI()
    app.include_router(create_rules_router(connection_factory=DatabaseConnectionFactory()))
    return TestClient(app)


def _seed(market_id: str = "m1", rules: str = "Resolve by official source https://sec.gov/x before 2026-06-01T00:00:00Z.") -> None:
    registry = MarketRegistry()
    registry.upsert_market(registry.normalize_market({"id": market_id, "question": "Will BTC close above 100k?", "category": "crypto", "active": True, "clobTokenIds": ["yes", "no"]}))
    store = MarketRulesStore()
    store.upsert_rules(store.extract_rules({"description": rules, "resolutionSourceUrl": "https://sec.gov/x", "endDate": "2026-06-01T00:00:00Z"}, market_id=market_id))


def test_rules_api_endpoints_and_analyze(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    _seed()
    assert client.get("/rules/coverage").status_code == 200
    assert client.get("/rules/analysis/recent").json()["count"] == 0
    assert client.get("/rules/blocks").json()["count"] == 0
    assert client.post("/rules/analyze", json={"market_id": "m1", "allow_ai": False}).status_code == 422
    response = client.post("/rules/analyze", json={"market_id": "m1", "allow_ai": False, "reason": "test"})
    assert response.status_code == 200
    assert response.json()["analysis"]["market_id"] == "m1"
    assert client.get("/rules/market/m1").status_code == 200

