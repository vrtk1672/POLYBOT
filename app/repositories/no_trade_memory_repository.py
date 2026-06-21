from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import NoTradeMemory
from app.repositories.market_memory_repository import _jsonable


class NoTradeMemoryRepository:
    def insert(self, conn: Connection, memory: NoTradeMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO no_trade_memory (
                market_id, market_family, candidate_engine, reason, observations_count,
                regret_rate, avg_would_have_roi, most_common_block_reason,
                no_trade_quality_score, confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.market_id, memory.market_family, memory.candidate_engine,
                memory.reason, memory.observations_count, memory.regret_rate,
                memory.avg_would_have_roi, memory.reason, memory.no_trade_quality_score,
                memory.confidence, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_memory ORDER BY confidence DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()

