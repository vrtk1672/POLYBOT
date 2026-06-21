from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "runtime_coordinator_decision_inputs",
            "runtime_coordinator_runs",
            "runtime_brain_output_inputs",
            "runtime_brain_producer_runs",
            "runtime_producer_evidence_items",
            "runtime_producer_evidence_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
            "coordinator_decision_conflicts",
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
                "notes": "runtime coordinator seed",
            },
        )


def _seed_runtime_brain_output() -> None:
    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)
    RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)


def test_runtime_coordinator_creates_runtime_decision_from_runtime_brain_output(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_brain_output()

    result = RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)

    assert result["mock_data"] is False
    assert result["input_runtime_brain_outputs"] == 1
    assert result["eligible_brain_outputs"] == 1
    assert result["coordinator_decisions_created"] == 1
    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0

    with DatabaseConnectionFactory().connect() as conn:
        decision = conn.execute("SELECT * FROM coordinator_decisions ORDER BY id DESC LIMIT 1").fetchone()
        inputs = conn.execute(
            "SELECT * FROM coordinator_decision_inputs WHERE coordinator_decision_id = %s",
            (decision["coordinator_decision_id"],),
        ).fetchall()

    assert decision["execution_allowed"] is False
    assert decision["metadata_json"]["producer_name"] == "runtime_coordinator_adapter"
    assert decision["metadata_json"]["generated_by"] == "runtime"
    assert decision["metadata_json"]["is_runtime_generated"] is True
    assert decision["metadata_json"]["is_dry_run_generated"] is False
    assert decision["metadata_json"]["source_brain_output_ids"]
    assert decision["metadata_json"]["paper_allowed"] is False
    assert decision["metadata_json"]["execution_allowed"] is False
    assert decision["metadata_json"]["order_intent_allowed"] is False
    assert len(inputs) == 1


def test_runtime_coordinator_is_idempotent_for_existing_runtime_brain_output(postgres_test_schema) -> None:
    _prepare()
    _seed_runtime_brain_output()

    first = RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)
    second = RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)

    assert first["coordinator_decisions_created"] == 1
    assert second["coordinator_decisions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions").fetchone()["count"]
    assert count == 1


def test_runtime_coordinator_dry_run_brain_outputs_are_ignored(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO brain_outputs (
                brain_output_id, brain, output_type, recommendation, confidence,
                risk_flags_json, metadata_json, generated_by, status, created_at, updated_at
            )
            VALUES (
                'dry-brain-1', 'runtime_brain_adapter', 'NO_TRADE_HINT', 'NO_TRADE_CANDIDATE',
                0.75, '[]'::jsonb, '{"is_runtime_generated": false, "is_dry_run_generated": true}'::jsonb,
                'mesh_dry_run', 'ACTIVE', now(), now()
            )
            """
        )

    result = RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)

    assert result["input_runtime_brain_outputs"] == 0
    assert result["coordinator_decisions_created"] == 0
