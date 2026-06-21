from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.data_foundation_routes import create_data_foundation_router
from app.data_foundation.market_registry import MarketRegistry
from app.data_foundation.market_rules_store import MarketRulesStore
from app.data_foundation.market_snapshotter_v2 import MarketSnapshotterV2
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema) -> TestClient:
    run_migrations()
    app = FastAPI()
    app.include_router(create_data_foundation_router(connection_factory=DatabaseConnectionFactory()))
    return TestClient(app)


def _seed() -> None:
    registry = MarketRegistry()
    record = registry.normalize_market({"id": "m1", "question": "Seed?", "active": True, "acceptingOrders": True, "clobTokenIds": ["yes", "no"]})
    registry.upsert_market(record)
    rules = MarketRulesStore()
    rules.upsert_rules(rules.extract_rules({"description": "rules", "resolutionSource": "official"}, market_id="m1"))
    snap = MarketSnapshotterV2().build_snapshot_from_market(
        {"market_id": "m1", "question": "Seed?", "yes_token_id": "yes", "no_token_id": "no", "yes_price": 0.5, "accepting_orders": True, "closed": False, "time_to_close_seconds": 100},
        rules={"rules_text": "rules"},
        liquidity={"liquidity_score": 10},
    )
    MarketSnapshotterV2().persist_snapshot(snap)


def test_data_markets_and_market_detail_work(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    _seed()
    assert client.get("/data/markets").json()["count"] == 1
    detail = client.get("/data/markets/m1")
    assert detail.status_code == 200
    assert detail.json()["market"]["market_id"] == "m1"


def test_unknown_market_returns_404(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    assert client.get("/data/markets/nope").status_code == 404


def test_coverage_and_families_work_without_fake_data(postgres_test_schema) -> None:
    client = _client(postgres_test_schema)
    _seed()
    coverage = client.get("/data/coverage").json()
    families = client.get("/data/families").json()
    assert coverage["total_markets"] == 1
    assert families["count"] >= 1
