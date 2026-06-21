from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class AICacheRepository:
    def get_cached_response(self, conn: Connection, cache_key: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT *
            FROM ai_cache
            WHERE cache_key = %s
              AND (expires_at IS NULL OR expires_at > now())
            """,
            (cache_key,),
        ).fetchone()

    def store_cached_response(
        self,
        conn: Connection,
        *,
        cache_key: str,
        request_hash: str,
        task_type: str,
        response_json: dict[str, Any],
        market_id: str | None = None,
        prompt_version_id: str | None = None,
        model_name: str | None = None,
        confidence: float | None = None,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO ai_cache (
                cache_key, request_hash, task_type, market_id, prompt_version_id,
                model_name, response_json, confidence, expires_at, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cache_key) DO UPDATE SET
                response_json = EXCLUDED.response_json,
                confidence = EXCLUDED.confidence,
                expires_at = EXCLUDED.expires_at,
                metadata_json = EXCLUDED.metadata_json
            """,
            (
                cache_key,
                request_hash,
                task_type,
                market_id,
                prompt_version_id,
                model_name,
                Jsonb(response_json),
                confidence,
                expires_at,
                Jsonb(metadata or {}),
            ),
        )

    def increment_hit(self, conn: Connection, cache_key: str) -> None:
        conn.execute(
            """
            UPDATE ai_cache
            SET hit_count = hit_count + 1,
                last_hit_at = now()
            WHERE cache_key = %s
            """,
            (cache_key,),
        )

    def list_cache(
        self,
        conn: Connection,
        *,
        task_type: str | None = None,
        market_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if task_type:
            filters.append("task_type = %s")
            params.append(task_type)
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM ai_cache
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def cache_hit_rate(self, conn: Connection) -> float:
        row = conn.execute("SELECT COALESCE(SUM(hit_count), 0) AS hits, COUNT(*) AS entries FROM ai_cache").fetchone()
        hits = int(row["hits"] or 0)
        entries = int(row["entries"] or 0)
        return round(hits / max(hits + entries, 1), 4)
