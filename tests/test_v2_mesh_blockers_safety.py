from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.mesh_blockers import MeshBlockersService


def _count_table(table: str) -> int:
    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"] or 0)


def test_mesh_blockers_does_not_create_orders_or_enable_paper(postgres_test_schema) -> None:
    before = {
        "paper_orders": _count_table("paper_orders"),
        "shadow_orders": _count_table("shadow_orders"),
        "live_orders": _count_table("live_orders"),
    }

    payload = MeshBlockersService().get_mesh_blockers(limit=20)

    after = {
        "paper_orders": _count_table("paper_orders"),
        "shadow_orders": _count_table("shadow_orders"),
        "live_orders": _count_table("live_orders"),
    }
    assert payload["mock_data"] is False
    assert payload["paper_ready"] is False
    assert after == before


def test_mesh_blockers_does_not_create_order_intents(postgres_test_schema) -> None:
    factory = DatabaseConnectionFactory()
    with factory.connect() as conn:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", ("order_intents",)).fetchone()
        before_exists = bool(row and row["table_name"])

    payload = MeshBlockersService().get_mesh_blockers(limit=20)

    with factory.connect() as conn:
        row = conn.execute("SELECT to_regclass(%s) AS table_name", ("order_intents",)).fetchone()
        after_exists = bool(row and row["table_name"])
    assert payload["paper_ready"] is False
    assert after_exists == before_exists
