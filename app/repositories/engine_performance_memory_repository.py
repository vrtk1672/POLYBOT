from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import EnginePerformanceMemory
from app.repositories.market_memory_repository import _jsonable


class EnginePerformanceMemoryRepository:
    def insert(self, conn: Connection, memory: EnginePerformanceMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO engine_performance_memory (
                engine, market_family, observations_count, wins_count, losses_count, neutral_count,
                win_rate, avg_roi, avg_roi_per_hour, avg_hold_seconds, adverse_selection_rate,
                engine_score, confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.engine, memory.market_family, memory.observations_count, memory.wins_count,
                memory.losses_count, memory.neutral_count, memory.win_rate, memory.avg_roi,
                memory.avg_roi_per_hour, memory.avg_hold_seconds, memory.adverse_selection_rate,
                memory.engine_score, memory.confidence, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_performance_memory ORDER BY confidence DESC, engine_score DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()

