from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class NewsReliabilityRepository:
    def upsert_reliability(
        self,
        conn: Connection,
        *,
        source_id: str,
        category: str | None,
        total_events: int,
        linked_events: int,
        ignored_events: int,
        error_count: int,
        reliability_score: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_source_reliability (
                source_id, category, total_events, linked_events, ignored_events,
                error_count, reliability_score, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, category) DO UPDATE
            SET total_events = EXCLUDED.total_events,
                linked_events = EXCLUDED.linked_events,
                ignored_events = EXCLUDED.ignored_events,
                error_count = EXCLUDED.error_count,
                reliability_score = EXCLUDED.reliability_score,
                last_updated_at = now(),
                metadata_json = news_source_reliability.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                source_id,
                category,
                total_events,
                linked_events,
                ignored_events,
                error_count,
                reliability_score,
                Jsonb(metadata or {}),
            ),
        ).fetchone()

    def get_reliability(self, conn: Connection, source_id: str, category: str | None = None) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM news_source_reliability
            WHERE source_id = %s AND category IS NOT DISTINCT FROM %s
            """,
            (source_id, category),
        ).fetchone()

