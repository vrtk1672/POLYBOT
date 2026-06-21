from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_memory.contracts import RulesRiskMemory
from app.repositories.market_memory_repository import _jsonable


class RulesRiskMemoryRepository:
    def insert(self, conn: Connection, memory: RulesRiskMemory) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO rules_risk_memory (
                market_id, market_family, observations_count, avg_wording_risk,
                avg_dispute_risk, avg_resolution_clarity, ambiguous_terms_count,
                edge_case_count, rules_block_rate, rules_risk_score, confidence, summary_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                memory.market_id, memory.market_family, memory.observations_count,
                memory.avg_wording_risk, memory.avg_dispute_risk, memory.avg_resolution_clarity,
                memory.ambiguous_terms_count, memory.edge_case_count, memory.rules_block_rate,
                memory.rules_risk_score, memory.confidence, Jsonb(_jsonable(memory.summary)),
            ),
        ).fetchone()

    def list(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM rules_risk_memory ORDER BY rules_risk_score DESC, updated_at DESC LIMIT %s", (limit,)).fetchall()
