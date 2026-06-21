from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class AICostRepository:
    def record_cost(
        self,
        conn: Connection,
        *,
        model_name: str,
        provider: str,
        task_type: str,
        ai_request_id: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float = 0.0,
        actual_cost: float | None = None,
        currency: str = "USD",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        cost_id = f"ai_cost_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO ai_cost_ledger (
                cost_id, ai_request_id, model_name, provider, task_type,
                input_tokens, output_tokens, estimated_cost, actual_cost,
                currency, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cost_id,
                ai_request_id,
                model_name,
                provider,
                task_type,
                input_tokens,
                output_tokens,
                estimated_cost,
                actual_cost,
                currency,
                Jsonb(metadata or {}),
            ),
        )
        return cost_id

    def summarize_costs(
        self,
        conn: Connection,
        *,
        model: str | None = None,
        task_type: str | None = None,
    ) -> dict[str, Any]:
        filters: list[str] = []
        params: list[Any] = []
        if model:
            filters.append("model_name = %s")
            params.append(model)
        if task_type:
            filters.append("task_type = %s")
            params.append(task_type)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        total = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(estimated_cost), 0) AS estimated,
                COALESCE(SUM(actual_cost), 0) AS actual,
                COUNT(*) FILTER (WHERE provider = 'cloud') AS cloud_calls,
                COUNT(*) FILTER (WHERE provider = 'local') AS local_calls,
                COALESCE(SUM(estimated_cost) FILTER (WHERE provider = 'cloud' AND created_at::date = CURRENT_DATE), 0) AS cloud_cost_today
            FROM ai_cost_ledger
            {where}
            """,
            params,
        ).fetchone()
        by_model = conn.execute(
            f"""
            SELECT model_name, provider, COALESCE(SUM(estimated_cost), 0) AS estimated_cost, COUNT(*) AS calls
            FROM ai_cost_ledger
            {where}
            GROUP BY model_name, provider
            ORDER BY estimated_cost DESC, calls DESC
            """,
            params,
        ).fetchall()
        by_task = conn.execute(
            f"""
            SELECT task_type, COALESCE(SUM(estimated_cost), 0) AS estimated_cost, COUNT(*) AS calls
            FROM ai_cost_ledger
            {where}
            GROUP BY task_type
            ORDER BY estimated_cost DESC, calls DESC
            """,
            params,
        ).fetchall()
        return {
            "total_estimated_cost": float(total["estimated"] or 0),
            "total_actual_cost": float(total["actual"] or 0),
            "cloud_cost_today": float(total["cloud_cost_today"] or 0),
            "cloud_calls_today": int(total["cloud_calls"] or 0),
            "local_calls_today": int(total["local_calls"] or 0),
            "cost_by_model": [dict(row) for row in by_model],
            "cost_by_task": [dict(row) for row in by_task],
        }

    def daily_totals(self, conn: Connection) -> dict[str, float | int]:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(estimated_cost), 0) AS total_cost,
                COALESCE(SUM(estimated_cost) FILTER (WHERE provider = 'cloud'), 0) AS cloud_cost,
                COUNT(*) FILTER (WHERE provider = 'cloud') AS cloud_calls
            FROM ai_cost_ledger
            WHERE created_at::date = CURRENT_DATE
            """
        ).fetchone()
        return {
            "total_cost": float(row["total_cost"] or 0),
            "cloud_cost": float(row["cloud_cost"] or 0),
            "cloud_calls": int(row["cloud_calls"] or 0),
        }
