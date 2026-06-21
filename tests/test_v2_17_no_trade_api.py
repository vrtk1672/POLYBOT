from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.no_trade_routes import create_no_trade_router
from app.main import create_app
from test_v2_17_fixtures import no_trade_payload


def test_no_trade_api_routes_load():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/no-trade/health" in paths
    assert "/no-trade/log" in paths


def test_no_trade_log_dry_run_writes_nothing():
    app = FastAPI()
    app.include_router(create_no_trade_router())
    client = TestClient(app)
    response = client.post("/no-trade/log", json={**no_trade_payload(), "dry_run": True})
    assert response.status_code == 200
    assert response.json()["written"] is False


def test_no_trade_log_without_reason_rejected():
    app = FastAPI()
    app.include_router(create_no_trade_router())
    client = TestClient(app)
    payload = no_trade_payload(primary_reason=None, reasons=[])
    payload["dry_run"] = True
    response = client.post("/no-trade/log", json=payload)
    assert response.status_code == 422

