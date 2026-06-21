from __future__ import annotations

from typing import Any

from psycopg import Connection


class PositionMonitor:
    def orphan_orders(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        if conn.execute("SELECT to_regclass(%s) AS name", ("orders_v2",)).fetchone()["name"] is None:
            return []
        if conn.execute("SELECT to_regclass(%s) AS name", ("exit_plans",)).fetchone()["name"] is None:
            return conn.execute("SELECT * FROM orders_v2 WHERE order_status IN ('SUBMITTED_PAPER','PLANNED_SHADOW','PARTIALLY_FILLED','FILLED') ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
        return conn.execute(
            """
            SELECT o.*
            FROM orders_v2 o
            LEFT JOIN exit_plans p ON p.order_id=o.order_id OR p.exit_plan_id=o.exit_plan_id
            WHERE o.order_status IN ('SUBMITTED_PAPER','PLANNED_SHADOW','PARTIALLY_FILLED','FILLED')
              AND p.id IS NULL
            ORDER BY o.created_at DESC, o.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

