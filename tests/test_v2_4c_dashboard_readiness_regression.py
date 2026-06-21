"""
V2 Neural Mesh Part 4C-H: Dashboard Readiness Regression Suite.

Validates requirements 35-38:
35. /dashboard/api/v2/mesh contains all required 4C layers
36. All 4C dashboard endpoints return mock_data=False
37. readiness.blocked_by is non-empty while paper_ready=False
38. Dashboard does not hide DEGRADED/BLOCKED status
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

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


def _prepare_minimal() -> None:
    """Seed minimal state: run migrations and create one signal."""
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_link_coverage_runs")
        conn.execute("DELETE FROM signal_suggested_market_links")
        conn.execute("DELETE FROM signal_link_coverage_analysis")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM signal_processing_states")
        conn.execute("DELETE FROM signal_processing_state_history")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
    NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="rules_resolution_truth",
            status="ACTIVE",
            market_id="dashboard-regression-market",
            confidence=0.8,
            strength=0.8,
            evidence={"resolution_status": "clear"},
            raw_payload_ref="rules:dashboard-regression",
        )
    )


# ===========================================================================
# Test 35: /dashboard/api/v2/mesh contains all key 4C layers
# ===========================================================================

REQUIRED_4C_LAYERS = (
    "signal_quality",
    "signal_processing",
    "link_coverage",
    "lineage_coverage",
    "dry_run_provenance",
    "mesh_blockers",
    "producer_health",
)

REQUIRED_CORE_LAYERS = (
    "sources",
    "neurons",
    "signals",
    "lineage",
    "brain_outputs",
    "coordinator",
)


def test_mesh_dashboard_contains_all_required_4c_layers(postgres_test_schema) -> None:
    """Test 35a: /dashboard/api/v2/mesh must include all 7 required 4C layers."""
    _prepare_minimal()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False

    for layer in REQUIRED_4C_LAYERS:
        assert layer in payload["layers"], f"Layer '{layer}' missing from mesh dashboard"


def test_mesh_dashboard_contains_all_required_core_layers(postgres_test_schema) -> None:
    """Test 35b: /dashboard/api/v2/mesh must include all core mesh layers."""
    _prepare_minimal()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200

    for layer in REQUIRED_CORE_LAYERS:
        assert layer in payload["layers"], f"Core layer '{layer}' missing from mesh dashboard"


def test_mesh_dashboard_all_layers_have_mock_data_false(postgres_test_schema) -> None:
    """Test 35c: Every layer in /dashboard/api/v2/mesh must return mock_data=False."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    assert payload["mock_data"] is False
    for layer_name, layer_data in payload["layers"].items():
        if isinstance(layer_data, dict) and "mock_data" in layer_data:
            assert layer_data["mock_data"] is False, (
                f"Layer '{layer_name}' returned mock_data=True"
            )


# ===========================================================================
# Test 36: All 4C dashboard endpoints return mock_data=False
# ===========================================================================

DASHBOARD_4C_ENDPOINTS = (
    "/dashboard/api/v2/signal-quality",
    "/dashboard/api/v2/signal-processing",
    "/dashboard/api/v2/link-coverage",
    "/dashboard/api/v2/lineage-coverage",
    "/dashboard/api/v2/dry-run-provenance",
    "/dashboard/api/v2/mesh-blockers",
    "/dashboard/api/v2/producer-health",
    "/dashboard/api/v2/mesh",
)


def test_all_4c_dashboard_endpoints_return_mock_data_false(postgres_test_schema) -> None:
    """Test 36: Every 4C dashboard endpoint must return mock_data=False."""
    _prepare_minimal()

    with _client() as client:
        for endpoint in DASHBOARD_4C_ENDPOINTS:
            response = client.get(endpoint)
            assert response.status_code == 200, f"Endpoint {endpoint} returned {response.status_code}"
            payload = response.json()
            assert payload.get("mock_data") is False, (
                f"Endpoint {endpoint} returned mock_data={payload.get('mock_data')}"
            )


def test_all_4c_dashboard_endpoints_return_paper_ready_false(postgres_test_schema) -> None:
    """Test 36b: Every 4C dashboard endpoint that has paper_ready must return False."""
    _prepare_minimal()

    paper_ready_endpoints = (
        "/dashboard/api/v2/signal-processing",
        "/dashboard/api/v2/link-coverage",
        "/dashboard/api/v2/mesh-blockers",
        "/dashboard/api/v2/producer-health",
        "/dashboard/api/v2/mesh",
    )

    with _client() as client:
        for endpoint in paper_ready_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200
            payload = response.json()
            if "paper_ready" in payload:
                assert payload["paper_ready"] is False, (
                    f"Endpoint {endpoint} returned paper_ready=True"
                )
            if "readiness" in payload and "paper_ready" in payload["readiness"]:
                assert payload["readiness"]["paper_ready"] is False, (
                    f"Endpoint {endpoint} readiness.paper_ready=True"
                )


# ===========================================================================
# Test 37: readiness.blocked_by is non-empty while paper_ready=False
# ===========================================================================

def test_mesh_readiness_blocked_by_is_non_empty(postgres_test_schema) -> None:
    """Test 37: When paper_ready=False, readiness.blocked_by must be non-empty."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    assert payload["readiness"]["paper_ready"] is False
    assert payload["readiness"]["blocked_by"], (
        "readiness.blocked_by must be non-empty when paper_ready=False"
    )


def test_mesh_blockers_endpoint_blocked_by_non_empty_when_paper_not_ready(postgres_test_schema) -> None:
    """Test 37b: /dashboard/api/v2/mesh-blockers must show active blockers."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh-blockers").json()

    assert payload["paper_ready"] is False
    assert payload["blocked_by"], (
        "mesh-blockers blocked_by must be non-empty when paper_ready=False"
    )
    assert payload["overall_status"] in ("BLOCKED", "DEGRADED"), (
        f"mesh-blockers overall_status must be BLOCKED or DEGRADED, got {payload['overall_status']}"
    )


# ===========================================================================
# Test 38: Dashboard does not hide DEGRADED/BLOCKED status
# ===========================================================================

def test_mesh_dashboard_does_not_report_ok_when_blockers_exist(postgres_test_schema) -> None:
    """Test 38: When active blockers exist, readiness.overall_status must not be READY."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    blocked_by = payload["readiness"].get("blocked_by", [])
    if blocked_by:
        assert payload["readiness"]["paper_ready"] is False
        assert payload["readiness"].get("overall_status") != "READY", (
            "overall_status must not be READY when blocked_by is non-empty"
        )


def test_mesh_blockers_overall_status_not_ready_when_active_blockers(postgres_test_schema) -> None:
    """Test 38b: /dashboard/api/v2/mesh-blockers must not return READY with active blockers."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh-blockers").json()

    if payload.get("blocked_by"):
        assert payload["overall_status"] != "READY", (
            "overall_status must not be READY when blocked_by is non-empty"
        )
        assert payload["paper_ready"] is False


def test_dry_run_provenance_endpoint_does_not_hide_dry_run_status(postgres_test_schema) -> None:
    """Test 38c: /dashboard/api/v2/dry-run-provenance correctly represents dry-run truth."""
    _prepare_minimal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/dry-run-provenance").json()

    assert payload["mock_data"] is False
    assert "brain_outputs_runtime" in payload or "summary" in payload or "data_source" in payload, (
        "dry-run-provenance endpoint must include brain output counts or summary"
    )


# ===========================================================================
# Cross-layer: safety from the dashboard layer
# ===========================================================================

def test_calling_all_dashboard_endpoints_does_not_create_orders(postgres_test_schema) -> None:
    """Consolidated: calling every 4C dashboard endpoint must not create orders."""
    _prepare_minimal()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
            "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
            "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        }

    with _client() as client:
        for endpoint in DASHBOARD_4C_ENDPOINTS:
            client.get(endpoint)

    with factory.connect() as conn:
        after = {
            "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
            "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
            "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        }

    assert after == before, (
        f"Dashboard endpoints must not create orders. Before={before}, After={after}"
    )
