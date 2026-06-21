from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.execution_v2_routes import create_execution_v2_router
from app.main import create_app
from test_v2_15_fixtures import approved_payload


def test_execution_api_routes_load():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/execution/health" in paths
    assert "/execution/paper/simulate" in paths


def test_execution_api_precheck_and_dry_run():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_execution_v2_router())
    client = TestClient(app)
    response = client.post("/execution/precheck", json={"market_id": "m1", "execution_mode": "PAPER_SIM", "exit_plan_id": "exit", "manual_input": approved_payload()})
    assert response.status_code == 200
    response = client.post("/execution/paper/simulate", json={"market_id": "m1", "dry_run": True, "exit_plan_id": "exit", "manual_input": approved_payload()})
    assert response.status_code == 200
    assert response.json()["written"] is False

