from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AIDecisionRepository:
    def insert_decision(
        self,
        conn: Connection,
        *,
        ai_decision_id: str,
        correlation_id: str,
        task_type: str,
        decision_type: str,
        output_json: dict[str, Any],
        ai_request_id: str | None = None,
        market_id: str | None = None,
        event_id: str | None = None,
        confidence: float | None = None,
        risk_flags: list[str] | None = None,
        cannot_trade_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_decision_logs (
                ai_decision_id, ai_request_id, market_id, event_id, correlation_id,
                task_type, decision_type, output_json, confidence, risk_flags_json,
                cannot_trade_reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ai_decision_id) DO NOTHING
            """,
            (
                ai_decision_id,
                ai_request_id,
                market_id,
                event_id,
                correlation_id,
                task_type,
                decision_type,
                Jsonb(output_json),
                confidence,
                Jsonb(risk_flags or []),
                cannot_trade_reason,
                Jsonb(metadata or {}),
            ),
        )

    def list_decisions(
        self,
        conn: Connection,
        *,
        market_id: str | None = None,
        task_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        if task_type:
            filters.append("task_type = %s")
            params.append(task_type)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM ai_decision_logs
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
