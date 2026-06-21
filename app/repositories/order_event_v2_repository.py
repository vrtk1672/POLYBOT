from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class OrderEventV2Repository:
    def insert(self, conn: Connection, *, order_id: str, event_type: str, reason: str, old_status: str | None = None, new_status: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO order_events_v2 (event_id, order_id, event_type, old_status, new_status, reason, details_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (f"order_event_v2_{uuid4().hex}", order_id, event_type, old_status, new_status, reason, Jsonb(details or {})),
        ).fetchone()

    def for_order(self, conn: Connection, order_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM order_events_v2 WHERE order_id=%s ORDER BY created_at ASC, id ASC", (order_id,)).fetchall()

