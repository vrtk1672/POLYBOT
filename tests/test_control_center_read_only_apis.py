from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.truth_contract import ControlCenterStatus, ControlCenterTruthState


CONTROL_CENTER_ENDPOINTS = (
    "/dashboard/api/v2/control/overview",
    "/dashboard/api/v2/control/organs",
    "/dashboard/api/v2/control/live-flow",
    "/dashboard/api/v2/control/decision-xray",
    "/dashboard/api/v2/control/blockers",
    "/dashboard/api/v2/control/closest-actionable",
    "/dashboard/api/v2/control/truth-state",
    "/dashboard/api/v2/control/risk-evidence",
    "/dashboard/api/v2/control/lifecycle-governance",
    "/dashboard/api/v2/control/mesh-dialogues",
    "/dashboard/api/v2/control/pnl-ledger",
    "/dashboard/api/v2/control/positions",
    "/dashboard/api/v2/control/no-trade",
    "/dashboard/api/v2/control/ai",
    "/dashboard/api/v2/control/logs",
    "/dashboard/api/v2/control/runtime-readiness",
    "/dashboard/api/v2/control/supervisor-life-path",
    "/dashboard/api/v2/control/candidate-producer-freshness",
    "/dashboard/api/v2/control/paper-readiness",
    "/dashboard/api/v2/control/candidate-explanations",
    "/dashboard/api/v2/control/eligible-intent-bridge",
    "/dashboard/api/v2/control/orderbook-price-readiness",
    "/dashboard/api/v2/control/candidate-price-path",
    "/dashboard/api/v2/control/event-mesh-proof",
    "/dashboard/api/v2/control/mesh-evidence-bundles",
)

REQUIRED_FIELDS = {
    "status",
    "source",
    "last_updated",
    "stale_after_seconds",
    "truth_state",
    "data",
    "warnings",
    "errors",
}


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


def test_all_control_center_read_only_endpoints_return_truth_contract_shape() -> None:
    valid_statuses = {item.value for item in ControlCenterStatus}
    valid_truth_states = {item.value for item in ControlCenterTruthState}
    with _client() as client:
        for endpoint in CONTROL_CENTER_ENDPOINTS:
            response = client.get(endpoint)
            assert response.status_code == 200, endpoint
            payload = response.json()
            assert REQUIRED_FIELDS <= set(payload), endpoint
            assert payload["status"] in valid_statuses, endpoint
            assert payload["truth_state"] in valid_truth_states, endpoint
            assert isinstance(payload["data"], dict), endpoint
            assert isinstance(payload["warnings"], list), endpoint
            assert isinstance(payload["errors"], list), endpoint
            if payload["status"] in {"REAL", "STALE", "PARTIAL"}:
                assert payload["source"], endpoint
            if payload["status"] == "ERROR":
                assert payload["errors"], endpoint


def test_control_center_routes_are_get_only_and_do_not_expose_mutating_actions() -> None:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    route_methods = {
        route.path: set(getattr(route, "methods", set()))
        for route in app.routes
        if getattr(route, "path", "").startswith("/dashboard/api/v2/control/")
    }
    for endpoint in CONTROL_CENTER_ENDPOINTS:
        assert route_methods[endpoint] == {"GET"}, endpoint

    forbidden_mutating_paths = (
        "/dashboard/api/v2/control/actions/system-on",
        "/dashboard/api/v2/control/actions/system-off",
        "/dashboard/api/v2/control/actions/start-full-monitor-run",
        "/dashboard/api/v2/control/actions/stop-current-run",
        "/dashboard/api/v2/control/actions/kill-switch",
        "/dashboard/api/v2/control/actions/enable-paper-simulation",
        "/dashboard/api/v2/control/actions/disable-paper-simulation",
        "/dashboard/api/v2/control/actions/reset-paper-balance",
        "/dashboard/api/v2/control/actions/execute-order",
        "/dashboard/api/v2/control/actions/create-order",
        "/dashboard/api/v2/control/actions/create-fill",
        "/dashboard/api/v2/control/actions/create-position",
        "/dashboard/api/v2/control/actions/shadow-live",
        "/dashboard/api/v2/control/actions/live",
    )
    with _client() as client:
        for endpoint in CONTROL_CENTER_ENDPOINTS:
            body = client.get(endpoint).text.lower()
            for path in forbidden_mutating_paths:
                assert path not in body, (endpoint, path)


def test_control_center_read_only_apis_avoid_fake_status_claims() -> None:
    forbidden_terms = ("green", "system online", "runtime status: healthy", "approved to trade")
    with _client() as client:
        for endpoint in CONTROL_CENTER_ENDPOINTS:
            body = client.get(endpoint).text.lower()
            for term in forbidden_terms:
                assert term not in body, (endpoint, term)


def test_domain_specific_endpoint_guards_are_reflected_in_sources_and_payloads() -> None:
    with _client() as client:
        pnl = client.get("/dashboard/api/v2/control/pnl-ledger").json()
        organs = client.get("/dashboard/api/v2/control/organs").json()
        decision = client.get("/dashboard/api/v2/control/decision-xray").json()
        closest = client.get("/dashboard/api/v2/control/closest-actionable").json()

    assert "ledger" in pnl["source"] or "capital" in pnl["source"]
    assert "fake_pnl" in pnl["data"]
    assert pnl["data"]["fake_pnl"] is False

    assert "heartbeat" in organs["source"] or "service_health" in organs["source"]
    assert organs["status"] in {"REAL", "MISSING", "PARTIAL", "STALE", "ERROR"}
    assert "healthy" not in str(organs).lower()

    assert "evidence" in decision["source"] or "source" in decision["source"]
    assert decision["data"].get("approval_claimed") is False

    candidates = closest["data"].get("candidates") or []
    for candidate in candidates:
        assert candidate.get("truth_state") in {item.value for item in ControlCenterTruthState}


def test_stage_5_preserves_stage_4_truth_contract_endpoint() -> None:
    with _client() as client:
        response = client.get("/dashboard/api/v2/control/truth-contract")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "NOT_IMPLEMENTED"
    assert REQUIRED_FIELDS <= set(payload)
