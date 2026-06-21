from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.exit_routes import create_exit_router
from app.main import create_app
from test_v2_16_fixtures import exit_plan_manual


def test_exit_api_routes_load():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/exits/health" in paths
    assert "/exits/plan" in paths


def test_exit_api_plan_dry_run_writes_nothing():
    app = FastAPI()
    app.include_router(create_exit_router())
    client = TestClient(app)
    response = client.post("/exits/plan", json={"market_id": "m1", "dry_run": True, "manual_input": exit_plan_manual()})
    assert response.status_code == 200
    assert response.json()["written"] is False

