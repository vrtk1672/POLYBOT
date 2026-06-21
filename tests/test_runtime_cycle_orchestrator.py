from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository
from app.runtime.cycle_orchestrator import RuntimeCycleOrchestrator
from app.runtime.modes import RuntimeMode
from app.runtime.state_governor import StateGovernor


def _setup(postgres_test_schema):
    run_migrations()
    factory = DatabaseConnectionFactory()
    governor = StateGovernor(connection_factory=factory)
    governor.ensure_initial_state()
    return factory, governor


def test_cycle_start_writes_runtime_cycles_v2(postgres_test_schema) -> None:
    factory, _ = _setup(postgres_test_schema)
    orchestrator = RuntimeCycleOrchestrator(connection_factory=factory)
    cycle_id = orchestrator.start_cycle()
    with factory.connect() as conn:
        row = conn.execute("SELECT * FROM runtime_cycles_v2 WHERE cycle_id = %s", (cycle_id,)).fetchone()
    assert row is not None
    assert row["mode"] == "DATA_ONLY"


def test_cycle_finish_updates_status_and_duration(postgres_test_schema) -> None:
    factory, _ = _setup(postgres_test_schema)
    orchestrator = RuntimeCycleOrchestrator(connection_factory=factory)
    cycle_id = orchestrator.start_cycle()
    orchestrator.finish_cycle(status="COMPLETED")
    with factory.connect() as conn:
        row = conn.execute("SELECT * FROM runtime_cycles_v2 WHERE cycle_id = %s", (cycle_id,)).fetchone()
    assert row["status"] == "COMPLETED"
    assert row["duration_ms"] >= 0


def test_kill_marks_cycle_blocked(postgres_test_schema) -> None:
    factory, governor = _setup(postgres_test_schema)
    governor.activate_kill(actor="operator", reason="stop")
    orchestrator = RuntimeCycleOrchestrator(connection_factory=factory)
    cycle_id = orchestrator.start_cycle()
    with factory.connect() as conn:
        row = conn.execute("SELECT * FROM runtime_cycles_v2 WHERE cycle_id = %s", (cycle_id,)).fetchone()
    assert row["blocked_by_mode"] is True


def test_data_only_allows_scanner_but_blocks_paper_live(postgres_test_schema) -> None:
    factory, _ = _setup(postgres_test_schema)
    orchestrator = RuntimeCycleOrchestrator(connection_factory=factory)
    orchestrator.start_cycle()
    assert orchestrator.should_run_stage("scanner")
    assert not orchestrator.should_run_stage("paper")
    assert not orchestrator.should_run_stage("live")


def test_paper_allows_paper_stage_and_blocks_live(postgres_test_schema) -> None:
    factory, governor = _setup(postgres_test_schema)
    governor.request_mode_change(RuntimeMode.PAPER, actor="operator", reason="paper validation")
    orchestrator = RuntimeCycleOrchestrator(connection_factory=factory)
    orchestrator.start_cycle()
    assert orchestrator.should_run_stage("paper")
    assert not orchestrator.should_run_stage("live")
