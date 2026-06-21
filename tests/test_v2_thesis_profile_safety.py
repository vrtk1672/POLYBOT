from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.thesis_profiles import ThesisProfileService


def test_thesis_profile_build_creates_no_executable_artifacts(postgres_test_schema) -> None:
    run_migrations()
    before = _counts()

    result = ThesisProfileService().build_profiles(limit=10, write_profiles=True)

    after = _counts()
    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    assert after == before


def _counts() -> dict[str, int | str]:
    with DatabaseConnectionFactory().connect() as conn:
        counts: dict[str, int | str] = {}
        for table in ("paper_orders", "shadow_orders", "live_orders", "order_intents", "positions"):
            exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
            counts[table] = "absent" if not exists else int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
        exists = conn.execute("SELECT to_regclass('coordinator_decisions') AS table_name").fetchone()["table_name"]
        counts["execution_allowed_true"] = 0 if not exists else int(conn.execute("SELECT COUNT(*) AS count FROM coordinator_decisions WHERE execution_allowed IS TRUE").fetchone()["count"] or 0)
    return counts
