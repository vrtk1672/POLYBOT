from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class RulesAIAnalysisRepository:
    def insert_analysis(self, conn: Connection, *, market_id: str, rules_analysis_id: str | None, ai_request_id: str | None, task_type: str, analysis: dict[str, Any], confidence: float | None, risk_flags: list[str] | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO rules_ai_analysis (
                rules_ai_analysis_id, market_id, rules_analysis_id, ai_request_id,
                task_type, analysis_json, confidence, risk_flags_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (f"rules_ai_{uuid4().hex}", market_id, rules_analysis_id, ai_request_id, task_type, Jsonb(analysis), confidence, Jsonb(risk_flags or []), Jsonb({})),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM rules_ai_analysis WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT %s", (market_id, limit)).fetchall()

