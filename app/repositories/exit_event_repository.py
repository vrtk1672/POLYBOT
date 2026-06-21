from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class ExitEventRepository:
    def insert(self, conn: Connection, *, event_type: str, reason: str, exit_plan_id: str | None = None, exit_intent_id: str | None = None, order_id: str | None = None, market_id: str | None = None, old_status: str | None = None, new_status: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO exit_events (
                event_id, exit_plan_id, exit_intent_id, order_id, market_id,
                event_type, old_status, new_status, reason, details_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                f"exit_event_{uuid4().hex}",
                exit_plan_id,
                exit_intent_id,
                order_id,
                market_id,
                event_type,
                old_status,
                new_status,
                reason,
                Jsonb(details or {}),
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_plan(self, conn: Connection, exit_plan_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_events WHERE exit_plan_id=%s ORDER BY created_at DESC, id DESC", (exit_plan_id,)).fetchall()

