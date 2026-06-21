from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.impact_graph import ImpactGraphService
from app.services.neuron_signals import NeuronSignalService
from app.services.query.dashboard_v2_query_service import DashboardV2QueryService


class _DummyMarketService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok"}

    async def top_markets(self, limit: int | None = None) -> list[object]:
        return []

    async def raw_counts(self) -> dict[str, object]:
        return {"raw_market_count": 0}

    async def last_refresh(self) -> dict[str, object]:
        return {"last_refresh_at": None}


def _clear() -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM position_thesis_profiles")
        conn.execute("DELETE FROM signal_position_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM entity_market_links")
        conn.execute("DELETE FROM event_entities")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _client() -> TestClient:
    app = FastAPI()
    app.state.market_service = _DummyMarketService()
    app.include_router(create_router())
    return TestClient(app)


def _seed_graph() -> None:
    signal = NeuronSignalService().create_signal(
        NeuronSignal(neuron="rules", event_type="rules_resolution_status_observed", status="ACTIVE", raw_direction="neutral", market_id="m-dash")
    )
    service = ImpactGraphService()
    service.link_signal_to_market(
        {
            "signal_id": signal["signal_id"],
            "market_id": "m-dash",
            "link_type": "exact_match",
            "link_status": "confirmed",
        }
    )
    thesis = service.create_position_thesis_profile(
        {"position_id": "p-dash", "market_id": "m-dash", "entry_thesis": "Dashboard truth thesis."}
    )
    service.create_impact_link(
        {
            "signal_id": signal["signal_id"],
            "market_id": "m-dash",
            "position_id": "p-dash",
            "thesis_id": thesis["thesis_id"],
            "impact_scope": "position",
            "impact_direction": "neutral",
            "impact_status": "suggested",
            "cortex_action_hint": "WATCH",
        }
    )


def test_dashboard_impact_graph_empty_truth(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        response = client.get("/dashboard/api/v2/impact-graph")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["entities_total"] == 0
    assert payload["impact_links_total"] == 0


def test_dashboard_impact_graph_reports_counts(postgres_test_schema) -> None:
    _clear()
    _seed_graph()

    with _client() as client:
        response = client.get("/dashboard/api/v2/impact-graph")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mock_data"] is False
    assert payload["signal_market_links_total"] == 1
    assert payload["impact_links_total"] == 1
    assert payload["positions_with_thesis"] == 1


def test_dashboard_v2_page_includes_impact_graph(postgres_test_schema) -> None:
    _clear()
    _seed_graph()

    payload = DashboardV2QueryService().get_page("impact-graph")

    assert payload["status"] == "OK"
    assert payload["data_source"]["mock_data"] is False
    assert payload["data"]["impact_graph"]["impact_links_total"] == 1
