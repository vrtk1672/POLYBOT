from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AIModelPerformanceRepository:
    def record_result(
        self,
        conn: Connection,
        *,
        model_name: str,
        provider: str,
        task_type: str,
        latency_ms: int | None = None,
        confidence: float | None = None,
        estimated_cost: float = 0.0,
        cache_hit: bool = False,
        failure: bool = False,
        escalation: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_model_performance (
                model_name, provider, task_type, total_requests, cache_hits,
                failures, escalations, avg_latency_ms, avg_confidence,
                estimated_total_cost, usefulness_score, metadata_json
            )
            VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_name, provider, task_type) DO UPDATE SET
                total_requests = ai_model_performance.total_requests + 1,
                cache_hits = ai_model_performance.cache_hits + EXCLUDED.cache_hits,
                failures = ai_model_performance.failures + EXCLUDED.failures,
                escalations = ai_model_performance.escalations + EXCLUDED.escalations,
                avg_latency_ms = COALESCE((ai_model_performance.avg_latency_ms + EXCLUDED.avg_latency_ms) / 2, ai_model_performance.avg_latency_ms, EXCLUDED.avg_latency_ms),
                avg_confidence = COALESCE((ai_model_performance.avg_confidence + EXCLUDED.avg_confidence) / 2, ai_model_performance.avg_confidence, EXCLUDED.avg_confidence),
                estimated_total_cost = ai_model_performance.estimated_total_cost + EXCLUDED.estimated_total_cost,
                usefulness_score = EXCLUDED.usefulness_score,
                last_updated_at = now(),
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                model_name,
                provider,
                task_type,
                1 if cache_hit else 0,
                1 if failure else 0,
                1 if escalation else 0,
                latency_ms,
                confidence,
                estimated_cost,
                _usefulness(confidence, failure),
                Jsonb(metadata or {}),
            ),
        )

    def list_summary(self, conn: Connection, limit: int = 20) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM ai_model_performance
            ORDER BY last_updated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()


def _usefulness(confidence: float | None, failure: bool) -> float:
    if failure:
        return 0.0
    return round(float(confidence if confidence is not None else 0.5), 4)
