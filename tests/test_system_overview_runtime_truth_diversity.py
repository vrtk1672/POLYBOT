from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.control_center.system_overview import _runtime_truth
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_system_overview_distinguishes_active_completed_and_stale_abandoned_cycles(postgres_test_schema) -> None:
    run_migrations()
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM runtime_cycles_v2")
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, finished_at, metadata_json)
            VALUES
              ('fresh-active', 'PAPER', 'RUNNING', %s, NULL, '{}'::jsonb),
              ('last-completed', 'PAPER', 'COMPLETED', %s, %s, '{}'::jsonb),
              ('old-abandoned', 'PAPER', 'STALE_ABANDONED', %s, %s, '{}'::jsonb)
            """,
            (
                now - timedelta(seconds=30),
                now - timedelta(minutes=2),
                now - timedelta(minutes=1),
                now - timedelta(hours=2),
                now - timedelta(hours=1, minutes=59),
            ),
        )
        tables = _table_cache(conn)
        truth = _runtime_truth(conn, tables)

    assert truth["current_active_cycle_id"] == "fresh-active"
    assert truth["latest_completed_cycle_id"] == "last-completed"
    assert truth["stale_abandoned_cycles_count"] == 1


def _table_cache(conn) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        """
    ).fetchall()
    cache: dict[str, set[str]] = {}
    for row in rows:
        cache.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return cache
