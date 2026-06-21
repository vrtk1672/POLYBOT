from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.impact_graph_routes import create_impact_graph_router
from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.neuron_signals import NeuronSignalService


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
    app.include_router(create_impact_graph_router())
    return TestClient(app)


def _signal() -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(neuron="market", event_type="source_status_observed", status="ACTIVE", raw_direction="neutral", market_id="m-api")
    )


def test_impact_graph_api_empty_truth(postgres_test_schema) -> None:
    _clear()

    with _client() as client:
        entities = client.get("/impact/entities").json()
        unlinked = client.get("/impact/unlinked-signals").json()

    assert entities["mock_data"] is False
    assert entities["count"] == 0
    assert unlinked["mock_data"] is False
    assert unlinked["count"] == 0


def test_impact_graph_api_creates_and_reads_links(postgres_test_schema) -> None:
    _clear()
    signal = _signal()

    with _client() as client:
        entity_response = client.post(
            "/impact/entities",
            json={"entity_type": "topic", "entity_name": "macro policy", "source_signal_id": signal["signal_id"], "confidence": 0.6},
        )
        entity = entity_response.json()["entity"]
        signal_market = client.post(
            "/impact/link/signal-market",
            json={
                "signal_id": signal["signal_id"],
                "market_id": "m-api",
                "link_type": "exact_match",
                "link_status": "confirmed",
                "confidence": 0.8,
            },
        ).json()["link"]
        signal_position = client.post(
            "/impact/link/signal-position",
            json={
                "signal_id": signal["signal_id"],
                "position_id": "p-api",
                "market_id": "m-api",
                "link_type": "manual",
                "link_status": "suggested",
            },
        ).json()["link"]
        thesis = client.post(
            "/impact/positions/p-api/thesis",
            json={"market_id": "m-api", "entry_thesis": "A neutral thesis profile for audit."},
        ).json()["thesis"]
        impact = client.post(
            "/impact/links",
            json={
                "signal_id": signal["signal_id"],
                "entity_id": entity["entity_id"],
                "market_id": "m-api",
                "position_id": "p-api",
                "thesis_id": thesis["thesis_id"],
                "impact_scope": "position",
                "impact_direction": "mixed",
                "impact_status": "needs_review",
                "cortex_action_hint": "REVIEW",
            },
        ).json()["impact_link"]
        by_entity = client.get(f"/impact/entities/{entity['entity_id']}").json()
        by_signal_market = client.get(f"/impact/signals/{signal['signal_id']}/markets").json()
        by_signal_position = client.get(f"/impact/signals/{signal['signal_id']}/positions").json()
        by_market = client.get("/impact/markets/m-api").json()
        by_position = client.get("/impact/positions/p-api").json()
        by_thesis = client.get("/impact/positions/p-api/thesis").json()
        by_link = client.get(f"/impact/links/{impact['impact_link_id']}").json()

    assert entity_response.status_code == 200
    assert signal_market["market_id"] == "m-api"
    assert signal_position["position_id"] == "p-api"
    assert by_entity["entity"]["entity_name"] == "macro policy"
    assert by_signal_market["count"] == 1
    assert by_signal_position["count"] == 1
    assert by_market["count"] == 1
    assert by_position["count"] == 1
    assert by_thesis["thesis"]["thesis_id"] == thesis["thesis_id"]
    assert by_link["impact_link"]["cortex_action_hint"] == "REVIEW"
