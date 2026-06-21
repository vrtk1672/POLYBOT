from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.strategy_routes import create_strategy_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations

def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_strategy_router(connection_factory=factory))
    return TestClient(app), factory


def _manual():
    return {
        "side": "YES",
        "opportunity_score": 0.82,
        "opportunity_score_band": "STRONG",
        "candidate_engines_from_opportunity": ["SAFE", "STRIKE", "CONVEX"],
        "opportunity_components": {"confidence": 0.86, "trigger_strength": 0.8, "repricing_potential": 0.76, "time_efficiency": 0.72, "liquidity_quality": 0.84, "exit_probability": 0.86, "convexity": 0.72, "wording_risk": 0.05, "risk_penalty": 0.1, "trap_risk": 0.1, "capital_allowed": True},
        "context_output": {"context_shift": True},
        "capital_output": {"capital_allowed": True, "max_position_size_usd": 500},
        "technical_truth": {"orderbook_signal": {"has_bid_ask": True, "depth_2c": 800}},
        "data_completeness_score": 1.0,
    }


def test_strategy_api_endpoints_and_dry_run(postgres_test_schema):
    client, factory = _client(postgres_test_schema)
    assert client.get("/strategy/health").status_code == 200
    dry = client.post("/strategy/route", json={"market_id": "api_strategy", "dry_run": True, "manual_input": _manual()})
    assert dry.status_code == 200
    assert dry.json()["written"] is False
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM strategy_routes_v2").fetchone()["count"] == 0
    write = client.post("/strategy/route", json={"market_id": "api_strategy", "dry_run": False, "manual_input": _manual()})
    assert write.status_code == 200
    run_id = write.json()["result"]["run_id"]
    for path in (
        "/strategy/market/api_strategy",
        "/strategy/recent",
        "/strategy/engines",
        "/strategy/rejections/recent",
        "/strategy/cooldowns",
        f"/strategy/run/{run_id}",
    ):
        response = client.get(path)
        assert response.status_code == 200
    assert client.get(f"/strategy/run/{run_id}").json()["engine_decisions"]
