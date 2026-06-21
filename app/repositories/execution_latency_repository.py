from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection


class ExecutionLatencyRepository:
    def insert(self, conn: Connection, *, latency_id: str, order_id: str | None, market_id: str | None, stage: str, latency_ms: float, started_at: datetime, finished_at: datetime) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO execution_latency (latency_id, order_id, market_id, stage, latency_ms, started_at, finished_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (latency_id, order_id, market_id, stage, latency_ms, started_at, finished_at),
        ).fetchone()

