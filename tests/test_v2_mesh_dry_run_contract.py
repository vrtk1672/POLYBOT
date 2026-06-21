from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.mesh_dry_run import MeshDryRunService


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


def test_dry_run_empty_data_is_non_executing(postgres_test_schema) -> None:
    _prepare()

    result = MeshDryRunService().run_first_intelligence_dry_run(limit=5)

    assert result["mock_data"] is False
    assert result["execution_allowed"] is False
    assert result["orders_created"] == 0
    assert result["markets_processed"] == 0
    assert result["signals_processed"] == 0
    assert result["safety"]["paper_orders"] == 0
    assert result["safety"]["shadow_orders"] == 0
    assert result["safety"]["live_orders"] == 0


def test_dry_run_ledger_persists_non_executing_state(postgres_test_schema) -> None:
    _prepare()

    result = MeshDryRunService().run_first_intelligence_dry_run(limit=5)
    stored = MeshDryRunService().get_dry_run(result["dry_run_id"])

    assert stored is not None
    assert stored["execution_allowed"] is False
    assert stored["summary"]["orders_created"] if "orders_created" in stored["summary"] else 0 == 0
    assert stored["items"] == []
