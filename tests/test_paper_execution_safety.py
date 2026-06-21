from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory

from test_paper_execution_service import _prepare, _seed_intent, _service


def test_paper_execution_does_not_create_real_or_live_artifacts(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()
    before = _counts()

    result = _service().run_execution(correlation_id="safety")
    after = _counts()

    assert result["status"] == "OK"
    assert after["orders_v2"] == before["orders_v2"]
    assert after["fills_v2"] == before["fills_v2"]
    assert after["positions"] == before["positions"]
    assert after["live_orders"] == before["live_orders"]
    assert result["real_orders_delta"] == 0
    assert result["live_orders_delta"] == 0
    assert result["fills_v2_delta"] == 0
    assert result["positions_delta"] == 0


def _counts() -> dict[str, int]:
    with DatabaseConnectionFactory().connect() as conn:
        return {
            "orders_v2": _count(conn, "orders_v2"),
            "fills_v2": _count(conn, "fills_v2"),
            "positions": _count(conn, "positions"),
            "live_orders": _count(conn, "live_orders"),
        }


def _count(conn, table: str) -> int:
    if not conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"]:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
