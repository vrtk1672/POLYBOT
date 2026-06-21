from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.neural_mesh.contracts import NeuronSignal
from app.neural_mesh.lineage import SignalLineage
from app.repositories.signal_lineage_repository import SignalLineageRepository
from app.services.lineage_coverage import LineageCoverageService
from app.services.neuron_signals import NeuronSignalService


def _prepare(*, dry_run: bool = False) -> dict[str, object]:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM signal_lineage_coverage_runs")
        conn.execute("DELETE FROM signal_lineage_coverage_analysis")
        conn.execute("DELETE FROM signal_quality_evaluations")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
    signal = NeuronSignalService().create_signal(
        NeuronSignal(
            signal_id="safety-lineage-signal",
            neuron="rules",
            event_type="rules_resolution_status_observed",
            source_name="mesh_dry_run" if dry_run else "rules_resolution_truth",
            status="ACTIVE",
            confidence=0.8,
            strength=0.8,
            evidence={"generated_by": "mesh_dry_run"} if dry_run else {"resolution_status": "clear"},
            raw_payload_ref="rules:safety",
            correlation_id="corr-safety-lineage",
        )
    )
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        SignalLineageRepository().attach_signal_binding(
            conn,
            SignalLineage(
                signal_id=str(signal["signal_id"]),
                neuron_name="rules",
                producer_name="mesh_dry_run" if dry_run else "rules_resolution_adapter",
                source_name="mesh_dry_run" if dry_run else "rules_resolution_truth",
                source_event_id="evt-safety",
                correlation_id="corr-safety-lineage",
                raw_payload_ref="rules:safety",
                generated_from="manual" if dry_run else "rules_resolution",
                lineage={"generated_by": "mesh_dry_run"} if dry_run else {"raw_payload_policy": "reference_only"},
            ),
        )
    return signal


def test_dry_run_lineage_does_not_count_as_paper_evidence(postgres_test_schema) -> None:
    signal = _prepare(dry_run=True)

    result = LineageCoverageService().analyze_signal(str(signal["signal_id"]))

    assert result is not None
    assert result["lineage_status"] == "DRY_RUN_ONLY"
    assert result["can_feed_paper_by_lineage"] is False


def test_lineage_coverage_does_not_create_orders_or_enable_paper(postgres_test_schema) -> None:
    signal = _prepare()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = _safety_counts(conn)

    LineageCoverageService().analyze_signal(str(signal["signal_id"]))

    with factory.connect() as conn:
        after = _safety_counts(conn)
    assert after == before


def _safety_counts(conn) -> dict[str, int]:
    return {
        "paper_orders": int(conn.execute("SELECT COUNT(*) AS count FROM paper_orders").fetchone()["count"]),
        "shadow_orders": int(conn.execute("SELECT COUNT(*) AS count FROM shadow_orders").fetchone()["count"]),
        "live_orders": int(conn.execute("SELECT COUNT(*) AS count FROM live_orders").fetchone()["count"]),
        "order_intents": _table_count(conn, "order_intents"),
        "execution_allowed": int(conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"]),
    }


def _table_count(conn, table_name: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()["count"])
