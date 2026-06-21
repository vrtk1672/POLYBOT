from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class NewsAIAnalysisRepository:
    def insert_analysis(
        self,
        conn: Connection,
        *,
        news_event_id: str,
        market_id: str | None,
        ai_request_id: str | None,
        task_type: str,
        analysis: dict[str, Any],
        confidence: float | None,
        risk_flags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_ai_analysis (
                news_ai_analysis_id, news_event_id, market_id, ai_request_id,
                task_type, analysis_json, confidence, risk_flags_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                f"news_ai_{uuid4().hex}",
                news_event_id,
                market_id,
                ai_request_id,
                task_type,
                Jsonb(analysis),
                confidence,
                Jsonb(risk_flags or []),
                Jsonb(metadata or {}),
            ),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT * FROM news_ai_analysis
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

