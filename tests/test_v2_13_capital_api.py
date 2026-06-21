from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.capital_routes import create_capital_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_capital_router(connection_factory=factory))
    return TestClient(app), factory


def _capital():
    return {"total_capital_usd": 1000, "available_capital_usd": 1000, "realized_pnl_usd": 100}


def _route():
    return {
        "id": 12,
        "run_id": "api_strategy",
        "market_id": "capital_api_m1",
        "side": "YES",
        "selected_engine": "SAFE",
        "route_status": "ROUTED",
        "route_confidence": 0.9,
        "max_position_size_usd": 75,
        "max_loss_usd": 20,
        "engine_contract_json": {"max_position_size_usd": 75, "max_loss_usd": 20},
    }


def test_capital_api_endpoints_and_dry_run(postgres_test_schema):
    client, factory = _client(postgres_test_schema)
    assert client.get("/capital/health").status_code == 200
    dry = client.post("/capital/state/rebuild", json={"dry_run": True, "manual_capital": _capital()})
    assert dry.status_code == 200
    assert dry.json()["written"] is False
    write_state = client.post("/capital/state/rebuild", json={"dry_run": False, "manual_capital": _capital()})
    assert write_state.status_code == 200
    dry_alloc = client.post("/capital/allocate", json={"market_id": "capital_api_m1", "dry_run": True, "manual_route": _route(), "manual_capital": _capital()})
    assert dry_alloc.status_code == 200
    write_alloc = client.post("/capital/allocate", json={"market_id": "capital_api_m1", "dry_run": False, "manual_route": _route(), "manual_capital": _capital()})
    assert write_alloc.status_code == 200
    dry_reinvest = client.post("/capital/reinvest/evaluate", json={"dry_run": True, "realized_profit_usd": 100})
    write_reinvest = client.post("/capital/reinvest/evaluate", json={"dry_run": False, "realized_profit_usd": 100})
    assert dry_reinvest.json()["written"] is False
    assert write_reinvest.json()["written"] is True
    for path in ("/capital/state", "/capital/budgets", "/capital/allocations/recent", "/capital/events/recent", "/capital/reinvest"):
        assert client.get(path).status_code == 200
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM capital_allocations_v2").fetchone()["count"] == 1

