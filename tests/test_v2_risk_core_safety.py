from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.risk_core import RiskCoreService


def _table_count(conn, table: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)


def _table_count_where(conn, table: str, where: str) -> int:
    exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]
    if not exists:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}").fetchone()["count"] or 0)


def test_risk_core_does_not_create_executable_artifacts(postgres_test_schema) -> None:
    run_migrations()
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        before = {
            "paper_orders": _table_count(conn, "paper_orders"),
            "shadow_orders": _table_count(conn, "shadow_orders"),
            "live_orders": _table_count(conn, "live_orders"),
            "order_intents": _table_count(conn, "order_intents"),
            "fills_v2": _table_count(conn, "fills_v2"),
            "positions": _table_count(conn, "positions"),
            "execution_allowed_true": _table_count_where(conn, "coordinator_decisions", "execution_allowed = true"),
        }

    result = RiskCoreService().evaluate_risk(limit=10, write_decisions=True)

    with factory.connect() as conn:
        after = {
            "paper_orders": _table_count(conn, "paper_orders"),
            "shadow_orders": _table_count(conn, "shadow_orders"),
            "live_orders": _table_count(conn, "live_orders"),
            "order_intents": _table_count(conn, "order_intents"),
            "fills_v2": _table_count(conn, "fills_v2"),
            "positions": _table_count(conn, "positions"),
            "execution_allowed_true": _table_count_where(conn, "coordinator_decisions", "execution_allowed = true"),
        }
        execution_allowed = _table_count(conn, "risk_decisions") and conn.execute(
            "SELECT COUNT(*) AS count FROM risk_decisions WHERE execution_allowed = true OR paper_candidate_allowed = true"
        ).fetchone()["count"]

    assert result["paper_ready_after"] is False
    assert result["orders_created"] == 0
    assert result["order_intents_created"] == 0
    assert result["fills_created"] == 0
    assert result["positions_created"] == 0
    assert result["live_actions_created"] == 0
    assert after == before
    assert int(execution_allowed or 0) == 0
