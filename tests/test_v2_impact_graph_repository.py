from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.neural_mesh.contracts import NeuronSignal
from app.services.impact_graph import ImpactGraphService
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


def _signal(market_id: str | None = "market-1") -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="ACTIVE",
            raw_direction="neutral",
            market_id=market_id,
            confidence=0.7,
            evidence={"resolution_source_status": "CLEAR"},
        )
    )


def test_impact_graph_repository_persists_core_links(postgres_test_schema) -> None:
    _clear()
    signal = _signal("market-graph")
    service = ImpactGraphService()

    entity = service.create_event_entity(
        {
            "entity_type": "organization",
            "entity_name": "Polymarket",
            "normalized_name": "polymarket",
            "source_signal_id": signal["signal_id"],
            "confidence": 0.8,
        }
    )
    entity_market = service.link_entity_to_market(
        {
            "entity_id": entity["entity_id"],
            "market_id": "market-graph",
            "link_type": "mentioned",
            "link_status": "confirmed",
            "confidence": 0.8,
            "evidence_signal_id": signal["signal_id"],
        }
    )
    signal_market = service.link_signal_to_market(
        {
            "signal_id": signal["signal_id"],
            "market_id": "market-graph",
            "link_type": "exact_match",
            "link_status": "confirmed",
            "confidence": 0.9,
            "reason": "Signal carried market_id.",
        }
    )
    signal_position = service.link_signal_to_position(
        {
            "signal_id": signal["signal_id"],
            "position_id": "position-graph",
            "market_id": "market-graph",
            "link_type": "manual",
            "link_status": "suggested",
            "confidence": 0.6,
        }
    )

    assert entity_market["entity_id"] == entity["entity_id"]
    assert signal_market["market_id"] == "market-graph"
    assert signal_position["position_id"] == "position-graph"
    assert service.get_entity(entity["entity_id"])["entity_name"] == "Polymarket"
    assert len(service.list_signal_market_links(signal["signal_id"])) == 1
    assert len(service.list_signal_position_links(signal["signal_id"])) == 1


def test_position_thesis_profile_and_impact_links(postgres_test_schema) -> None:
    _clear()
    signal = _signal("market-thesis")
    service = ImpactGraphService()
    thesis = service.create_position_thesis_profile(
        {
            "position_id": "position-thesis",
            "market_id": "market-thesis",
            "entry_thesis": "Position was opened for a documented asymmetric thesis.",
            "profit_drivers": ["resolution clarity"],
            "invalidation_drivers": ["wording ambiguity"],
            "watch_entities": ["issuer"],
            "danger_signals": ["rules degraded"],
            "status": "ACTIVE",
        }
    )
    impact = service.create_impact_link(
        {
            "signal_id": signal["signal_id"],
            "market_id": "market-thesis",
            "position_id": "position-thesis",
            "thesis_id": thesis["thesis_id"],
            "impact_scope": "thesis",
            "impact_direction": "neutral",
            "impact_status": "needs_review",
            "impact_strength": 0.4,
            "confidence": 0.7,
            "urgency": 0.2,
            "cortex_action_hint": "REVIEW",
            "reasoning_summary": "Rules signal links to thesis for review only.",
            "created_by": "test",
        }
    )

    assert service.get_position_thesis_profile("position-thesis")["thesis_id"] == thesis["thesis_id"]
    assert service.get_impact_link(impact["impact_link_id"])["cortex_action_hint"] == "REVIEW"
    assert len(service.list_market_impacts("market-thesis")) == 1
    assert len(service.list_position_impacts("position-thesis")) == 1


def test_list_unlinked_signals_and_summary(postgres_test_schema) -> None:
    _clear()
    linked = _signal("market-linked")
    unlinked = _signal(None)
    service = ImpactGraphService()
    service.link_signal_to_market(
        {
            "signal_id": linked["signal_id"],
            "market_id": "market-linked",
            "link_type": "exact_match",
            "link_status": "confirmed",
        }
    )

    unlinked_signals = service.list_unlinked_signals(limit=10)
    summary = service.get_impact_graph_summary()

    assert {item["signal_id"] for item in unlinked_signals} == {unlinked["signal_id"]}
    assert summary["mock_data"] is False
    assert summary["signal_market_links_total"] == 1
    assert summary["signals_without_market_link"] == 1


def test_impact_graph_store_does_not_mutate_order_tables(postgres_test_schema) -> None:
    _clear()
    signal = _signal("market-safe")
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }

    ImpactGraphService().create_impact_link(
        {
            "signal_id": signal["signal_id"],
            "market_id": "market-safe",
            "impact_scope": "market",
            "impact_direction": "unknown",
            "impact_status": "suggested",
            "cortex_action_hint": "WATCH",
        }
    )

    with factory.connect() as conn:
        after = {
            "paper_orders": conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"],
            "shadow_orders": conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"],
            "live_orders": conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"],
        }
    assert after == before
