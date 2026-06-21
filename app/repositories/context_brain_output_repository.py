from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.brains.contracts import ContextBrainOutput


class ContextBrainOutputRepository:
    def insert(self, conn: Connection, run_id: str, market_family: str | None, output: ContextBrainOutput, memory_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO context_brain_outputs (
                run_id, market_id, market_family, context_shift, direction, strength, confidence,
                already_priced_in_score, ttl_seconds, urgency_score, risk_score, risks_json,
                supporting_signals_json, contradicting_signals_json, memory_snapshot_json,
                ai_context_summary, explanation, insufficient_data, insufficient_data_reasons_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                run_id, output.market_id, market_family, output.context_shift, output.direction,
                output.strength, output.confidence, output.already_priced_in_score, output.ttl_seconds,
                output.urgency_score, output.risk_score, Jsonb(output.risks),
                Jsonb(_jsonable(output.supporting_signals)), Jsonb(_jsonable(output.contradicting_signals)),
                Jsonb(_jsonable(memory_snapshot or {})), output.ai_context_summary, output.explanation,
                output.insufficient_data, Jsonb(output.insufficient_data_reasons),
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM context_brain_outputs WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM context_brain_outputs ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))
