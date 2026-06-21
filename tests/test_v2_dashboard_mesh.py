from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


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


def _clear_mesh() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM position_thesis_validation_events")
        conn.execute("DELETE FROM position_thesis_profiles")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM entity_market_links")
        conn.execute("DELETE FROM event_entities")
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM neuron_health")
        conn.execute("DELETE FROM source_status")


def _seed_source_status() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO source_status (
                source_name, source_type, configured, key_required, key_present,
                endpoint_url, runtime_status, freshness_status, read_only,
                mutation_allowed, success_count, error_count, last_success_at,
                last_latency_ms, details_json, notes
            )
            VALUES (
                'polymarket_gamma', 'market_discovery', true, false, false,
                'persisted-test', 'ACTIVE', 'FRESH', true, false, 1, 0,
                now(), 12, '{}'::jsonb, 'persisted test source'
            )
            ON CONFLICT (source_name) DO UPDATE SET
                runtime_status = EXCLUDED.runtime_status,
                freshness_status = EXCLUDED.freshness_status,
                last_success_at = now(),
                updated_at = now()
            """
        )


def _seed_signal() -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="ACTIVE",
            raw_direction="neutral",
            market_id="mesh-market",
            confidence=0.8,
        )
    )


def test_mesh_dashboard_route_returns_real_truth(postgres_test_schema) -> None:
    _clear_mesh()
    _seed_source_status()
    _seed_signal()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["status"] in {"OK", "DEGRADED", "ERROR"}
    assert payload["runtime"]
    assert payload["mesh_summary"]["execution_allowed_count"] == 0


def test_mesh_dashboard_includes_required_layers(postgres_test_schema) -> None:
    _clear_mesh()
    _seed_source_status()
    _seed_signal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    for layer in (
        "sources",
        "neurons",
        "signals",
        "lineage",
        "impact_graph",
        "brain_outputs",
        "coordinator",
        "thesis",
        "opportunities",
        "no_trade",
        "exit",
        "ai",
    ):
        assert layer in payload["layers"]
        assert payload["layers"][layer]["mock_data"] is False


def test_mesh_dashboard_flow_and_readiness_are_conservative(postgres_test_schema) -> None:
    _clear_mesh()
    _seed_source_status()
    signal = _seed_signal()

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    assert payload["flow"]["latest_signals"]
    assert payload["flow"]["unlinked_signals"]
    assert payload["flow"]["unlinked_signals"][0]["signal_id"] == signal["signal_id"]
    assert payload["readiness"]["paper_ready"] is False
    assert "paper_full_evidence_loop_not_proven_in_part4a" in payload["readiness"]["blocked_by"]
    assert payload["readiness"]["blocked_by"]


def test_mesh_dashboard_empty_optional_data_does_not_crash(postgres_test_schema) -> None:
    _clear_mesh()

    with _client() as client:
        response = client.get("/dashboard/api/v2/mesh")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["layers"]["brain_outputs"]["latest_outputs"] == []
    assert payload["layers"]["coordinator"]["execution_allowed_count"] == 0
    assert payload["layers"]["thesis"]["latest_thesis_profiles"] == []
    assert payload["readiness"]["paper_ready"] is False


def test_mesh_dashboard_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear_mesh()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    with _client() as client:
        payload = client.get("/dashboard/api/v2/mesh").json()

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert payload["mock_data"] is False
    assert after == before
