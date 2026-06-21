from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.services.mesh_dry_run import MeshDryRunService
from app.services.neuron_signals import NeuronSignalService


def _prepare() -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute("DELETE FROM mesh_dry_run_items")
        conn.execute("DELETE FROM mesh_dry_runs")
        conn.execute("DELETE FROM coordinator_decision_conflicts")
        conn.execute("DELETE FROM coordinator_decision_inputs")
        conn.execute("DELETE FROM coordinator_decisions")
        conn.execute("DELETE FROM brain_output_conflicts")
        conn.execute("DELETE FROM brain_output_dependencies")
        conn.execute("DELETE FROM brain_outputs")
        conn.execute("DELETE FROM impact_links")
        conn.execute("DELETE FROM signal_market_links")
        conn.execute("DELETE FROM entity_market_links")
        conn.execute("DELETE FROM event_entities")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signal_evidence")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _signal() -> dict[str, object]:
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="DEGRADED",
            raw_direction="neutral",
            market_id="dry-market",
            confidence=0.72,
            evidence={"resolution_status": "ambiguous"},
            entity_count=1,
        )
    )
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO neuron_signal_entities (signal_id, entity_type, entity_name, entity_id, confidence)
            VALUES (%s, 'organization', 'Election Board', 'entity-election-board', 0.8)
            """,
            (signal["signal_id"],),
        )
    return signal


def test_dry_run_links_signal_market_and_entities(postgres_test_schema) -> None:
    _prepare()
    signal = _signal()

    result = MeshDryRunService().run_first_intelligence_dry_run(limit=10)

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        market_links = conn.execute("SELECT * FROM signal_market_links WHERE signal_id=%s", (signal["signal_id"],)).fetchall()
        entities = conn.execute("SELECT * FROM event_entities WHERE source_signal_id=%s", (signal["signal_id"],)).fetchall()
    assert result["signal_market_links_created"] == 1
    assert result["event_entities_created"] == 1
    assert len(market_links) == 1
    assert len(entities) == 1


def test_dry_run_persists_run_and_item_rows(postgres_test_schema) -> None:
    _prepare()
    _signal()

    result = MeshDryRunService().run_first_intelligence_dry_run(limit=10)
    stored = MeshDryRunService().get_dry_run(result["dry_run_id"])

    assert stored is not None
    assert stored["markets_processed"] == 1
    assert len(stored["items"]) == 1
    assert stored["items"][0]["market_id"] == "dry-market"
