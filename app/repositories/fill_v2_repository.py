from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.execution_v2.contracts import FillRecord


class FillV2Repository:
    def insert(self, conn: Connection, fill: FillRecord) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO fills_v2 (
                fill_id, order_id, market_id, side, fill_mode, fill_status, requested_size,
                filled_size, fill_price, expected_price, slippage_bps, fee_bps, fee_usd,
                fill_probability, liquidity_consumed_json, partial, failed_reason
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                fill.fill_id, fill.order_id, fill.market_id, fill.side, fill.fill_mode,
                fill.fill_status, fill.requested_size, fill.filled_size, fill.fill_price,
                fill.expected_price, fill.slippage_bps, fill.fee_bps, fill.fee_usd,
                fill.fill_probability, Jsonb(fill.liquidity_consumed), fill.partial,
                fill.failed_reason,
            ),
        ).fetchone()

    def for_order(self, conn: Connection, order_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM fills_v2 WHERE order_id=%s ORDER BY created_at ASC, id ASC", (order_id,)).fetchall()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM fills_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

