from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "runtime_producer_evidence_items",
            "runtime_producer_evidence_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
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
            conn.execute(f"DELETE FROM {table}")


def _seed_source_status() -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
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
                "details_json": {"local_observation": True},
                "latency_ms": 12,
                "notes": "test local source observation",
            },
        )


def test_runtime_evidence_run_creates_non_executing_runtime_signal_and_updates_truth_chain(postgres_test_schema) -> None:
    _prepare()
    _seed_source_status()

    result = RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)

    assert result["mock_data"] is False
    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["live_actions_created"] == 0
    assert result["signals_created"] == 1
    assert result["quality_updated"] == 1
    assert result["processing_updated"] == 1
    assert result["lineage_updated"] == 1
    assert result["link_coverage_updated"] == 1
    assert result["producer_health_updated"] is True
    assert result["mesh_blockers_updated"] is True

    signal_id = result["items"][0]["signal_id"]
    with DatabaseConnectionFactory().connect() as conn:
        signal = conn.execute("SELECT * FROM neuron_signals WHERE signal_id = %s", (signal_id,)).fetchone()
        binding = conn.execute("SELECT * FROM neuron_signal_bindings WHERE signal_id = %s", (signal_id,)).fetchone()
        quality = conn.execute("SELECT * FROM signal_quality_evaluations WHERE signal_id = %s", (signal_id,)).fetchone()
        processing = conn.execute("SELECT * FROM signal_processing_states WHERE signal_id = %s", (signal_id,)).fetchone()
        lineage = conn.execute("SELECT * FROM signal_lineage_coverage_analysis WHERE signal_id = %s", (signal_id,)).fetchone()
        link = conn.execute("SELECT * FROM signal_link_coverage_analysis WHERE signal_id = %s", (signal_id,)).fetchone()
        provenance = conn.execute(
            "SELECT * FROM dry_run_provenance_analysis WHERE object_type = 'SIGNAL' AND object_id = %s",
            (signal_id,),
        ).fetchone()

    assert signal["evidence_json"]["generated_by"] == "runtime"
    assert signal["evidence_json"]["is_runtime_generated"] is True
    assert signal["evidence_json"]["is_dry_run_generated"] is False
    assert binding["producer_name"] == "source_status_adapter"
    assert binding["lineage_json"]["generated_by"] == "runtime"
    assert quality["is_runtime_generated"] is True
    assert quality["is_dry_run_generated"] is False
    assert processing["can_feed_paper"] is False
    assert lineage["lineage_status"] in {"RUNTIME_VERIFIED", "COMPLETE"}
    assert link["can_feed_paper_after_link"] is False
    assert provenance["provenance_status"] == "RUNTIME_VERIFIED"


def test_runtime_evidence_dry_run_does_not_write_signals(postgres_test_schema) -> None:
    _prepare()
    _seed_source_status()

    result = RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, dry_run=True)

    assert result["status"] == "DRY_RUN"
    assert result["signals_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM neuron_signals").fetchone()["count"]
    assert count == 0
