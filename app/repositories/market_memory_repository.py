from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import MarketMemory


class MarketMemoryRepository:
    def upsert(self, conn: Connection, memory: MarketMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO market_memory_v2 (
                market_id, market_family, last_updated_at, observations_count, best_engine,
                best_engine_confidence, avg_price, avg_spread_bps, avg_depth_1c, avg_depth_2c,
                avg_depth_5c, avg_fill_rate, avg_slippage_bps, avg_hold_seconds, avg_exit_quality,
                avg_time_efficiency, false_signal_rate, technical_block_rate, liquidity_failure_rate,
                stale_data_rate, wording_risk_avg, dispute_risk_avg, memory_confidence, memory_status, summary_json
            )
            VALUES (%s, %s, now(), %s, %s, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id) DO UPDATE SET
                market_family = EXCLUDED.market_family,
                last_updated_at = now(),
                observations_count = EXCLUDED.observations_count,
                best_engine = EXCLUDED.best_engine,
                avg_price = EXCLUDED.avg_price,
                avg_spread_bps = EXCLUDED.avg_spread_bps,
                avg_depth_1c = EXCLUDED.avg_depth_1c,
                avg_depth_2c = EXCLUDED.avg_depth_2c,
                avg_depth_5c = EXCLUDED.avg_depth_5c,
                avg_fill_rate = EXCLUDED.avg_fill_rate,
                avg_slippage_bps = EXCLUDED.avg_slippage_bps,
                avg_hold_seconds = EXCLUDED.avg_hold_seconds,
                avg_exit_quality = EXCLUDED.avg_exit_quality,
                avg_time_efficiency = EXCLUDED.avg_time_efficiency,
                false_signal_rate = EXCLUDED.false_signal_rate,
                technical_block_rate = EXCLUDED.technical_block_rate,
                liquidity_failure_rate = EXCLUDED.liquidity_failure_rate,
                stale_data_rate = EXCLUDED.stale_data_rate,
                wording_risk_avg = EXCLUDED.wording_risk_avg,
                dispute_risk_avg = EXCLUDED.dispute_risk_avg,
                memory_confidence = EXCLUDED.memory_confidence,
                memory_status = EXCLUDED.memory_status,
                summary_json = EXCLUDED.summary_json,
                updated_at = now()
            RETURNING *
            """,
            (
                memory.market_id, memory.market_family, memory.observations_count, memory.best_engine,
                memory.avg_price, memory.avg_spread_bps, memory.avg_depth_1c, memory.avg_depth_2c,
                memory.avg_depth_5c, memory.avg_fill_rate, memory.avg_slippage_bps, memory.avg_hold_seconds,
                memory.avg_exit_quality, memory.avg_time_efficiency, memory.false_signal_rate,
                memory.technical_block_rate, memory.liquidity_failure_rate, memory.stale_data_rate,
                memory.wording_risk_avg, memory.dispute_risk_avg, memory.memory_confidence,
                memory.memory_status, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM market_memory_v2 WHERE market_id = %s ORDER BY updated_at DESC LIMIT 1", (market_id,)).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM market_memory_v2 ORDER BY updated_at DESC LIMIT %s", (limit,)).fetchall()

    def health(self, conn: Connection) -> dict[str, Any]:
        return conn.execute(
            """
            SELECT
                MAX(updated_at) AS last_update_ts,
                COUNT(*) FILTER (WHERE updated_at::date = CURRENT_DATE) AS memories_updated_today,
                COUNT(*) FILTER (WHERE memory_status = 'insufficient_data') AS insufficient_data_count
            FROM market_memory_v2
            """
        ).fetchone()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))

