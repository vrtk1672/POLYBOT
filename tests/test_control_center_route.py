from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "source": "dummy-market-service"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def test_control_center_route_falls_back_to_reserved_placeholder(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.control_center_index_path", lambda: None)

    with _client() as client:
        response = client.get("/control-center")

    assert response.status_code == 200
    assert "Control Center V1.5" in response.text
    assert "ROUTE_RESERVED" in response.text
    assert "NOT_IMPLEMENTED" in response.text
    assert "No live data is displayed on this placeholder" in response.text
    assert "no controls are active" in response.text
    assert "no trading, execution, paper, shadow, or live action" in response.text
    assert "/dashboard" in response.text
    assert "/dashboard/api/v2/*" in response.text


def test_control_center_placeholder_avoids_fake_status_claims(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.control_center_index_path", lambda: None)

    with _client() as client:
        response = client.get("/control-center")

    body = response.text.lower()
    forbidden_claims = (
        "healthy",
        "green",
        "pnl",
        "balance",
        "positions",
        "system online",
        "runtime status",
    )
    for claim in forbidden_claims:
        assert claim not in body


def test_control_center_serves_built_react_app_when_dist_exists(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text(
        '<!doctype html><div id="root"></div><script type="module" src="/control-center/assets/app.js"></script>',
        encoding="utf-8",
    )

    monkeypatch.setattr("app.api.routes.control_center_index_path", lambda: index)
    monkeypatch.setattr("app.api.routes.control_center_static_path", lambda asset_path: None)

    with _client() as client:
        response = client.get("/control-center")
        refresh_response = client.get("/control-center/decision-xray")

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text
    assert "/control-center/assets/app.js" in response.text
    assert refresh_response.status_code == 200
    assert '<div id="root"></div>' in refresh_response.text


def test_control_center_serves_static_assets_from_dist(tmp_path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    index = dist / "index.html"
    bundle = assets / "app.js"
    index.write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    bundle.write_text("console.log('control-center')", encoding="utf-8")

    monkeypatch.setattr("app.api.routes.control_center_index_path", lambda: index)
    monkeypatch.setattr(
        "app.api.routes.control_center_static_path",
        lambda asset_path: bundle if asset_path == "assets/app.js" else None,
    )

    with _client() as client:
        response = client.get("/control-center/assets/app.js")
        missing = client.get("/control-center/assets/missing.js")

    assert response.status_code == 200
    assert "control-center" in response.text
    assert missing.status_code == 404


def test_dashboard_remains_available() -> None:
    with _client() as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert "POLYBOT Operator Control Room" in response.text
