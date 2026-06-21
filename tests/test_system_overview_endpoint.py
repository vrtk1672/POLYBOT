from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.config import get_database_settings


def test_system_overview_endpoint_returns_full_safe_shape_without_db(monkeypatch) -> None:
    monkeypatch.delenv("POLYBOT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_database_settings.cache_clear()
    app = FastAPI()
    app.include_router(create_router())

    response = TestClient(app).get("/dashboard/api/v2/control/system-overview")

    get_database_settings.cache_clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "control_center:system_overview"
    assert payload["database"]["status"] == "DATABASE_UNAVAILABLE"
    assert payload["execution_mode"] in {"DISABLED", "DATA_ONLY", "PAPER"}
    assert payload["live_adapter_state"] == "BLOCKED"
    assert payload["market_universe"]["total"] == 0
    assert "sources_events" in payload
    assert "triggers" in payload
    assert "candidates" in payload
    assert "decisions" in payload
    assert "execution" in payload
    assert "pnl" in payload
    assert payload["safety"]["live_adapter_disabled"] is True


def test_system_overview_endpoint_is_registered() -> None:
    app = FastAPI()
    app.include_router(create_router())
    paths = {route.path for route in app.routes}
    assert "/dashboard/api/v2/control/system-overview" in paths
