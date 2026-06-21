from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.brain_routes import create_brain_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_brain_router(connection_factory=factory))
    return TestClient(app), factory


def _context_manual():
    return {"news_signals": [{"strength": 0.9, "confidence": 0.9, "direction": "YES"}], "memory_snapshot": {"confidence": 0.8}, "data_completeness_score": 1.0}


def _capital_manual():
    return {"balance": 1000, "available_capital": 800, "engine_budgets": {"strike": 100}, "risk_limits": {"min_cash_reserve_pct": 0.2, "max_alloc_pct": 0.1}, "memory_snapshot": {"confidence": 0.8}, "data_completeness_score": 1.0}


def test_brain_api_endpoints_and_writes(postgres_test_schema):
    client, factory = _client(postgres_test_schema)
    assert client.get("/brains/health").status_code == 200
    assert client.get("/brains/context/recent").status_code == 200
    assert client.get("/brains/capital/recent").status_code == 200
    assert client.get("/brains/blocked/recent").status_code == 200

    dry_context = client.post("/brains/context/analyze", json={"market_id": "api_m", "dry_run": True, "manual_input": _context_manual()})
    assert dry_context.status_code == 200
    assert dry_context.json()["written"] is False
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM context_brain_outputs").fetchone()["count"] == 0

    write_context = client.post("/brains/context/analyze", json={"market_id": "api_m", "dry_run": False, "manual_input": _context_manual()})
    assert write_context.status_code == 200
    assert write_context.json()["written"] is True
    assert client.get("/brains/context/market/api_m").json()["market_id"] == "api_m"

    dry_capital = client.post("/brains/capital/analyze", json={"market_id": "api_m", "candidate_engine": "strike", "dry_run": True, "manual_input": _capital_manual()})
    assert dry_capital.status_code == 200
    assert dry_capital.json()["written"] is False

    write_capital = client.post("/brains/capital/analyze", json={"market_id": "api_m", "candidate_engine": "strike", "dry_run": False, "manual_input": _capital_manual()})
    assert write_capital.status_code == 200
    assert write_capital.json()["written"] is True
    assert client.get("/brains/capital/market/api_m").json()["market_id"] == "api_m"

    both = client.post("/brains/analyze", json={"market_id": "api_both", "candidate_engine": "strike", "dry_run": False, "manual_context": _context_manual(), "manual_capital": _capital_manual()})
    assert both.status_code == 200
    assert both.json()["written"] is True
    assert client.get("/brains/market/api_both").status_code == 200
