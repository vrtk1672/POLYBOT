from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class ExecutionErrorRepository:
    def insert(self, conn: Connection, *, market_id: str | None, order_id: str | None, error_type: str, severity: str, message: str, context: dict[str, Any] | None = None, recoverable: bool = True) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO execution_errors (error_id, market_id, order_id, error_type, severity, message, context_json, recoverable)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (f"execution_error_{uuid4().hex}", market_id, order_id, error_type, severity, message, Jsonb(context or {}), recoverable),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM execution_errors ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

