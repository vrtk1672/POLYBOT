from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "runtime_brain_output_inputs",
            "runtime_brain_producer_runs",
            "runtime_producer_evidence_items",
            "runtime_producer_evidence_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_output_conflicts",
            "brain_outputs",
            "signal_link_coverage_runs",
            "signal_suggested_market_links",
            "signal_link_coverage_analysis",
            "signal_lineage_coverage_runs",
            "signal_lineage_coverage_analysis",
            "signal_processing_state_history",
            "signal_processing_states",
            "signal_quality_evaluations",
            "neuron_signal_bindings",
            "neuron_signals",
            "source_status",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        SourceStatusRepository().upsert_status(
            conn,
            {
                "source_name": "polymarket_gamma",
                "source_type": "market_discovery",
                "configured": True,
                "key_required": False,
                "key_present": False,
                "key_name": None,
                "endpoint_url": "local://source-status/polymarket_gamma",
                "runtime_status": "ACTIVE",
                "freshness_status": "FRESH",
                "read_only": True,
                "mutation_allowed": False,
                "details_json": {},
                "latency_ms": 1,
                "notes": "runtime brain seed",
            },
        )


def _seed_runtime_signal() -> None:
    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)


def test_runtime_brain_adapter_creates_runtime_brain_output_from_runtime_signal(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_signal()

    result = RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)

    assert result["mock_data"] is False
    assert result["input_runtime_signals"] == 1
    assert result["eligible_signals"] == 1
    assert result["brain_outputs_created"] == 1
    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    assert result["coordinator_runtime_decisions"] == 0

    with DatabaseConnectionFactory().connect() as conn:
        output = conn.execute("SELECT * FROM brain_outputs WHERE generated_by = 'runtime'").fetchone()
        deps = conn.execute("SELECT * FROM brain_output_dependencies WHERE brain_output_id = %s", (output["brain_output_id"],)).fetchall()

    assert output["brain"] == "runtime_brain_adapter"
    assert output["metadata_json"]["producer_name"] == "runtime_brain_adapter"
    assert output["metadata_json"]["generated_by"] == "runtime"
    assert output["metadata_json"]["is_runtime_generated"] is True
    assert output["metadata_json"]["is_dry_run_generated"] is False
    assert output["metadata_json"]["source_signal_ids"]
    assert output["metadata_json"]["paper_allowed"] is False
    assert output["metadata_json"]["execution_allowed"] is False
    assert len(deps) == 1


def test_runtime_brain_adapter_is_idempotent_for_existing_signal_output(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_signal()

    first = RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)
    second = RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)

    assert first["brain_outputs_created"] == 1
    assert second["brain_outputs_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM brain_outputs WHERE generated_by = 'runtime'").fetchone()["count"]
    assert count == 1


def test_runtime_brain_adapter_dry_run_signals_are_ignored(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO neuron_signals (signal_id, neuron, event_type, status, evidence_json, created_at, updated_at)
            VALUES ('dry-sig-1', 'market', 'source_status_observed', 'ACTIVE', '{"generated_by":"mesh_dry_run"}'::jsonb, now(), now())
            """
        )

    result = RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)

    assert result["input_runtime_signals"] == 0
    assert result["brain_outputs_created"] == 0
