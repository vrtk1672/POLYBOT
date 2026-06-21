from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository


def test_ttl_expired_active_cycle_becomes_stale_abandoned(postgres_test_schema) -> None:
    _prepare()
    old_started = datetime.now(UTC) - timedelta(hours=2)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, metadata_json)
            VALUES ('old-running-cycle', 'PAPER', 'RUNNING', %s, '{}'::jsonb)
            """,
            (old_started,),
        )
        changed = RuntimeCycleRepository().mark_stale_abandoned(
            conn,
            older_than=datetime.now(UTC) - timedelta(minutes=10),
            reason="pytest_ttl",
        )

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT status, finished_at, metadata_json FROM runtime_cycles_v2 WHERE cycle_id='old-running-cycle'").fetchone()

    assert changed == 1
    assert row["status"] == "STALE_ABANDONED"
    assert row["finished_at"] is not None
    assert row["metadata_json"]["cleanup_state"] == "STALE_ABANDONED"


def test_system_off_cleanup_marks_open_cycles_safe_stopped(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, metadata_json)
            VALUES ('fresh-running-cycle', 'PAPER', 'RUNNING', now(), '{}'::jsonb)
            """
        )
        changed = RuntimeCycleRepository().mark_open_cycles_safe_stopped(conn, reason="pytest_system_off")

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT status, finished_at, metadata_json FROM runtime_cycles_v2 WHERE cycle_id='fresh-running-cycle'").fetchone()

    assert changed == 1
    assert row["status"] == "SAFE_STOPPED"
    assert row["finished_at"] is not None
    assert row["metadata_json"]["cleanup_state"] == "SAFE_STOPPED"


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM runtime_cycles_v2")
