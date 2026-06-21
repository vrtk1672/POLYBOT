from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.exit_cortex.contracts import ExitQualityResult


class ExitQualityRepository:
    def insert(self, conn: Connection, quality: ExitQualityResult) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO exit_quality (
                quality_id, exit_plan_id, exit_intent_id, order_id, market_id,
                expected_exit_price, actual_exit_price, expected_slippage_bps,
                actual_slippage_bps, expected_exit_liquidity_score,
                actual_exit_fill_ratio, exit_latency_ms, exit_quality_score,
                quality_flags_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                quality.quality_id,
                quality.exit_plan_id,
                quality.exit_intent_id,
                quality.order_id,
                quality.market_id,
                quality.expected_exit_price,
                quality.actual_exit_price,
                quality.expected_slippage_bps,
                quality.actual_slippage_bps,
                quality.expected_exit_liquidity_score,
                quality.actual_exit_fill_ratio,
                quality.exit_latency_ms,
                quality.exit_quality_score,
                Jsonb(quality.quality_flags),
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_quality ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_plan(self, conn: Connection, exit_plan_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_quality WHERE exit_plan_id=%s ORDER BY created_at DESC, id DESC", (exit_plan_id,)).fetchall()

