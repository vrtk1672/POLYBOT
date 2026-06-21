from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.risk_routes import create_risk_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def _client(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    app = FastAPI()
    app.include_router(create_risk_router(connection_factory=factory))
    return TestClient(app), factory


def _manual():
    return {
        "engine": "SAFE",
        "strategy_route": {"market_id": "risk_api", "selected_engine": "SAFE", "route_status": "ROUTED", "route_confidence": 0.8, "target_exit": 0.8, "stop_loss": 0.3},
        "capital_allocation": {"allocation_id": "a1", "allocation_status": "ALLOCATED", "approved_size_usd": 10, "max_loss_usd": 5, "engine_budget_after_usd": 50},
        "governor_state": {"governor_status": "OK", "data_confidence": 1},
        "data_completeness_score": 1,
    }


def test_risk_api_endpoints_and_dry_run(postgres_test_schema):
    client, factory = _client(postgres_test_schema)
    assert client.get("/risk/health").status_code == 200
    dry = client.post("/risk/governor/rebuild", json={"dry_run": True, "manual_payload": {"daily_loss_usd": 0}})
    assert dry.status_code == 200
    assert dry.json()["written"] is False
    write = client.post("/risk/governor/rebuild", json={"dry_run": False, "manual_payload": {"daily_loss_usd": 0, "attack_mode_approval": False}})
    assert write.status_code == 200
    gate = client.post("/risk/gate/evaluate", json={"market_id": "risk_api", "dry_run": False, "manual_input": _manual()})
    assert gate.status_code == 200
    run_id = gate.json()["decision"]["run_id"]
    override = client.post("/risk/override", json={"actor": "op", "reason": "test", "scope": "ENGINE", "override_type": "SOFT_RISK", "dry_run": False})
    assert override.status_code == 200
    for path in ("/risk/governor", "/risk/limits", "/risk/breaches/recent", "/risk/cooldowns", "/risk/gate/recent", f"/risk/gate/{run_id}"):
        assert client.get(path).status_code == 200
    with factory.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_gate_decisions").fetchone()["count"] == 1
        assert conn.execute("SELECT COUNT(*) AS count FROM risk_governor_events WHERE event_type='risk.manual_override.created'").fetchone()["count"] == 1

