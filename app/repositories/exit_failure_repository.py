from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.exit_cortex.contracts import ExitFailure


class ExitFailureRepository:
    def insert(self, conn: Connection, failure: ExitFailure) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO exit_failures (
                failure_id, exit_plan_id, exit_intent_id, order_id, market_id,
                failure_type, severity, reason, recoverable, details_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                failure.failure_id,
                failure.exit_plan_id,
                failure.exit_intent_id,
                failure.order_id,
                failure.market_id,
                failure.failure_type,
                failure.severity,
                failure.reason,
                failure.recoverable,
                Jsonb(failure.details),
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_failures ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_plan(self, conn: Connection, exit_plan_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_failures WHERE exit_plan_id=%s ORDER BY created_at DESC, id DESC", (exit_plan_id,)).fetchall()
