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
        conn.execute("DELETE FROM event_entities")
        conn.execute("DELETE FROM neuron_signal_entities")
        conn.execute("DELETE FROM neuron_signals")


def _seed_rules_signal() -> dict[str, object]:
    return NeuronSignalService().create_signal(
        NeuronSignal(
            neuron="rules",
            event_type="rules_resolution_status_observed",
            status="DEGRADED",
            market_id="flow-market",
            raw_direction="neutral",
            confidence=0.8,
            evidence={"resolution_status": "ambiguous"},
        )
    )


def test_dry_run_creates_full_non_executing_flow(postgres_test_schema) -> None:
    _prepare()
    signal = _seed_rules_signal()

    result = MeshDryRunService().run_first_intelligence_dry_run(limit=10)

    assert result["markets_processed"] == 1
    assert result["impact_links_created"] == 1
    assert result["brain_outputs_created"] == 4
    assert result["coordinator_decisions_created"] == 1
    assert result["no_trade_explanations_created"] == 1
    sample = result["sample_results"][0]
    assert sample["coordinator_final_state"] in {"NO_TRADE", "REVIEW_REQUIRED", "RISK_BLOCKED", "INSUFFICIENT_DATA", "WATCH"}
    assert sample["execution_allowed"] is False
    assert sample["no_trade_explanation"]

    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        dependencies = conn.execute(
            "SELECT * FROM brain_output_dependencies WHERE dependency_type='signal' AND dependency_id=%s",
            (signal["signal_id"],),
        ).fetchall()
        execution_allowed = conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"]
    assert len(dependencies) == 4
    assert execution_allowed == 0


def test_dry_run_rerun_reuses_existing_links_and_outputs(postgres_test_schema) -> None:
    _prepare()
    _seed_rules_signal()

    first = MeshDryRunService().run_first_intelligence_dry_run(limit=10)
    second = MeshDryRunService().run_first_intelligence_dry_run(limit=10)

    assert first["signal_market_links_created"] == 1
    assert first["impact_links_created"] == 1
    assert first["brain_outputs_created"] == 4
    assert second["signal_market_links_created"] == 0
    assert second["impact_links_created"] == 0
    assert second["brain_outputs_created"] == 0
    assert second["coordinator_decisions_created"] == 0
