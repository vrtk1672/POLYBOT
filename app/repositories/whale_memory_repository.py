from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import WhaleMemory
from app.repositories.market_memory_repository import _jsonable


class WhaleMemoryRepository:
    def insert(self, conn: Connection, memory: WhaleMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO whale_memory (
                whale_id, market_family, observations_count, hit_rate, avg_timing_quality,
                avg_size_usd, follow_value_avg, noise_score_avg, reversal_rate, whale_score,
                confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.whale_id, memory.market_family, memory.observations_count, memory.hit_rate,
                memory.avg_timing_quality, memory.avg_size_usd, memory.follow_value_avg,
                memory.noise_score_avg, memory.reversal_rate, memory.whale_score,
                memory.confidence, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM whale_memory ORDER BY whale_score DESC, confidence DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()

