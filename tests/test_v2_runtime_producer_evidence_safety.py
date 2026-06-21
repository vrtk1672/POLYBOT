from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.source_status_repository import SourceStatusRepository
from app.services.mesh_blockers import MeshBlockersService
from app.services.runtime_producer_evidence import RuntimeProducerEvidenceService


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM runtime_producer_evidence_items")
        conn.execute("DELETE FROM runtime_producer_evidence_runs")
        conn.execute("DELETE FROM neuron_signal_bindings")
        conn.execute("DELETE FROM neuron_signals")
        conn.execute("DELETE FROM source_status")
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
                "notes": "runtime evidence safety seed",
            },
        )


def _count(conn, table: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def test_runtime_evidence_creates_no_orders_intents_fills_or_positions(postgres_test_schema) -> None:
    _prepare()

    result = RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)

    assert result["paper_ready_after"] is False
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "shadow_orders") == 0
        assert _count(conn, "live_orders") == 0
        assert _count(conn, "order_intents") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "positions") == 0
        execution_allowed = _count(conn, "coordinator_decisions")
    assert execution_allowed == 0


def test_runtime_evidence_keeps_risk_exit_and_orderbook_blockers_active(postgres_test_schema) -> None:
    _prepare()

    RuntimeProducerEvidenceService().run_runtime_evidence_loop(limit=10, apply_evaluations=True)
    blockers = MeshBlockersService().get_mesh_blockers(limit=20)

    assert blockers["paper_ready"] is False
    assert "ORDERBOOK_SNAPSHOTS_MISSING" in blockers["blocked_by"]
    assert "NO_RISK_CORE" in blockers["blocked_by"]
    assert "NO_EXIT_FOUNDATION" in blockers["blocked_by"]
