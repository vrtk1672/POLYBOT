from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import SourceReliabilityMemory
from app.repositories.market_memory_repository import _jsonable


class SourceReliabilityMemoryRepository:
    def insert(self, conn: Connection, memory: SourceReliabilityMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO source_reliability_memory (
                source_type, source_name, source_id, market_family, observations_count,
                true_positive_count, false_positive_count, avg_latency_seconds,
                reliability_score, usefulness_score, confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.source_type, memory.source_name, memory.source_id, memory.market_family,
                memory.observations_count, memory.true_positive_count, memory.false_positive_count,
                memory.avg_latency_seconds, memory.reliability_score, memory.usefulness_score,
                memory.confidence, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM source_reliability_memory ORDER BY confidence DESC, reliability_score DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()

