from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.execution_v2.contracts import ExecutionQualityResult


class ExecutionQualityRepository:
    def insert(self, conn: Connection, quality: ExecutionQualityResult) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO execution_quality (
                quality_id, order_id, market_id, expected_fill_price, actual_fill_price,
                expected_slippage_bps, actual_slippage_bps, expected_fill_probability,
                actual_fill_ratio, cancel_count, failed_fill_count, partial_fill_count,
                execution_quality_score, quality_flags_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                quality.quality_id, quality.order_id, quality.market_id, quality.expected_fill_price,
                quality.actual_fill_price, quality.expected_slippage_bps, quality.actual_slippage_bps,
                quality.expected_fill_probability, quality.actual_fill_ratio, quality.cancel_count,
                quality.failed_fill_count, quality.partial_fill_count, quality.execution_quality_score,
                Jsonb(quality.quality_flags),
            ),
        ).fetchone()

    def for_order(self, conn: Connection, order_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM execution_quality WHERE order_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (order_id,)).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM execution_quality ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

