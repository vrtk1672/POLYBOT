from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.opportunity_routes import create_opportunity_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_opportunity_router(connection_factory=factory))
    return TestClient(app), factory


def _manual():
    return {
        "context_output": {"strength": 0.9, "confidence": 0.9, "already_priced_in_score": 0.1},
        "capital_output": {"capital_allowed": True, "allocation_confidence": 0.9, "capital_recycling_score": 0.6},
        "market_signal": {"technical_score": 0.8, "data_completeness_score": 1.0},
        "orderbook_signal": {"has_bid_ask": True, "spread_bps": 80, "depth_2c": 500},
        "liquidity_signal": {"entry_liquidity_score": 0.8, "exit_liquidity_score": 0.8, "exit_quality_score": 0.8, "expected_slippage_bps": 70, "max_safe_size_usd": 1000},
        "market_memory": {"memory_confidence": 0.8},
        "data_completeness_score": 1.0,
    }


def test_opportunity_api_endpoints_and_dry_run(postgres_test_schema):
    client, factory = _client(postgres_test_schema)

    assert client.get("/opportunities/health").status_code == 200
    dry = client.post("/opportunities/score", json={"market_id": "api_opp", "dry_run": True, "manual_input": _manual()})
    assert dry.status_code == 200
    assert dry.json()["written"] is False
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM opportunity_scores_v2").fetchone()["count"] == 0

    write = client.post("/opportunities/score", json={"market_id": "api_opp", "dry_run": False, "manual_input": _manual()})
    assert write.status_code == 200
    run_id = write.json()["result"]["run_id"]
    assert client.get("/opportunities/market/api_opp").status_code == 200
    assert client.get("/opportunities/recent").status_code == 200
    assert client.get("/opportunities/top").status_code == 200
    assert client.get("/opportunities/blocked/recent").status_code == 200
    assert client.get("/opportunities/risk-flags/recent").status_code == 200
    detail = client.get(f"/opportunities/run/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["signal_inputs"]

