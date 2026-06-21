from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class CapitalEventRepository:
    def insert(
        self,
        conn: Connection,
        *,
        event_id: str,
        event_type: str,
        actor: str,
        reason: str,
        market_id: str | None = None,
        engine: str | None = None,
        bucket: str | None = None,
        amount_usd: float | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO capital_events (
                event_id, event_type, actor, market_id, engine, bucket, amount_usd,
                before_json, after_json, reason, correlation_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (event_id, event_type, actor, market_id, engine, bucket, amount_usd, Jsonb(before or {}), Jsonb(after or {}), reason, correlation_id),
        ).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM capital_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

