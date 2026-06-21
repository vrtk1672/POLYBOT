from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.cycle_orchestrator import RuntimeCycleOrchestrator


def test_cycle_start_marks_old_open_cycles_stale(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM runtime_cycles_v2")
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, metadata_json)
            VALUES ('old-open-cycle', 'PAPER', 'RUNNING', %s, '{}'::jsonb)
            """,
            (datetime.now(UTC) - timedelta(hours=1),),
        )

    RuntimeCycleOrchestrator().start_cycle(metadata={"source": "pytest"})

    with DatabaseConnectionFactory().connect() as conn:
        old_row = conn.execute("SELECT status, finished_at, metadata_json FROM runtime_cycles_v2 WHERE cycle_id='old-open-cycle'").fetchone()
        open_count = conn.execute(
            "SELECT COUNT(*) AS count FROM runtime_cycles_v2 WHERE finished_at IS NULL AND status IN ('RUNNING','STARTING')"
        ).fetchone()["count"]

    assert old_row["status"] == "STALE_ABANDONED"
    assert old_row["finished_at"] is not None
    assert old_row["metadata_json"]["cleanup_state"] == "STALE_ABANDONED"
    assert int(open_count) == 1
