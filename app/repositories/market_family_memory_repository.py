from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import MarketFamilyMemory
from app.repositories.market_memory_repository import _jsonable


class MarketFamilyMemoryRepository:
    def upsert(self, conn: Connection, memory: MarketFamilyMemory, *, category: str = "general") -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO market_family_memory (
                market_family, category, observations_count, markets_count, best_engine,
                avg_spread_bps, avg_depth_2c, avg_slippage_bps, technical_block_rate,
                memory_confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_family, category) DO UPDATE SET
                observations_count = EXCLUDED.observations_count,
                markets_count = EXCLUDED.markets_count,
                best_engine = EXCLUDED.best_engine,
                avg_spread_bps = EXCLUDED.avg_spread_bps,
                avg_depth_2c = EXCLUDED.avg_depth_2c,
                avg_slippage_bps = EXCLUDED.avg_slippage_bps,
                technical_block_rate = EXCLUDED.technical_block_rate,
                memory_confidence = EXCLUDED.memory_confidence,
                summary_json = EXCLUDED.summary_json,
                updated_at = now()
            RETURNING *
            """,
            (
                memory.market_family, category, memory.observations_count, memory.markets_count,
                memory.best_engine, memory.avg_spread_bps, memory.avg_depth_2c,
                memory.avg_slippage_bps, memory.technical_block_rate, memory.memory_confidence,
                Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def get(self, conn: Connection, market_family: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM market_family_memory WHERE market_family = %s ORDER BY updated_at DESC LIMIT 1", (market_family,)).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM market_family_memory ORDER BY memory_confidence DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()

