from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.mesh_blockers import MeshBlockersService
from app.services.runtime_brain_adapter import RuntimeBrainAdapterService
from app.services.runtime_coordinator import RuntimeCoordinatorDecisionService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


def _count(conn, table: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "runtime_coordinator_decision_inputs",
            "runtime_coordinator_runs",
            "runtime_brain_output_inputs",
            "runtime_brain_producer_runs",
            "dry_run_provenance_runs",
            "dry_run_provenance_analysis",
            "coordinator_decision_inputs",
            "coordinator_decisions",
            "brain_output_dependencies",
            "brain_output_conflicts",
            "brain_outputs",
            "neuron_signal_bindings",
            "neuron_signals",
            "source_status",
        ):
            if conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
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
                "notes": "runtime coordinator safety seed",
            },
        )
    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)
    RuntimeBrainAdapterService().run_runtime_brain(limit=10, write_outputs=True)


def test_runtime_coordinator_creates_no_orders_intents_fills_positions_or_live_actions(postgres_test_schema) -> None:
    _prepare()

    result = RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "shadow_orders") == 0
        assert _count(conn, "live_orders") == 0
        assert _count(conn, "order_intents") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "fills_v2") == 0
        assert _count(conn, "positions") == 0
        exec_allowed = conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed = true").fetchone()["count"]
        assert exec_allowed == 0


def test_runtime_coordinator_resolves_coordinator_runtime_blocker_but_keeps_risk_exit_orderbook(postgres_test_schema) -> None:
    _prepare()

    RuntimeCoordinatorDecisionService().run_runtime_coordinator(limit=10, write_decisions=True)
    blockers = MeshBlockersService().get_mesh_blockers(limit=20)

    assert blockers["paper_ready"] is False
    assert "NO_RUNTIME_COORDINATOR_DECISIONS" not in blockers["blocked_by"]
    assert "COORDINATOR_DECISIONS_DRY_RUN_ONLY" not in blockers["blocked_by"]
    assert "NO_RISK_CORE" in blockers["blocked_by"]
    assert "NO_EXIT_FOUNDATION" in blockers["blocked_by"]
    assert "ORDERBOOK_SNAPSHOTS_MISSING" in blockers["blocked_by"]
