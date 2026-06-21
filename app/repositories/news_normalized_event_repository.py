from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.news_neuron.contracts import NormalizedNewsEvent


class NewsNormalizedEventRepository:
    def upsert_event(self, conn: Connection, event: NormalizedNewsEvent) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_normalized_events (
                news_event_id, raw_event_id, source_id, dedup_group_id, title,
                normalized_title, summary, normalized_text, url, published_at,
                event_time, category, entities_json, topics_json, language,
                importance_score, urgency_score, novelty_score, source_reliability, status,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (news_event_id) DO UPDATE
            SET dedup_group_id = EXCLUDED.dedup_group_id,
                importance_score = EXCLUDED.importance_score,
                urgency_score = EXCLUDED.urgency_score,
                novelty_score = EXCLUDED.novelty_score,
                source_reliability = EXCLUDED.source_reliability,
                status = EXCLUDED.status,
                metadata_json = news_normalized_events.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                event.news_event_id,
                event.raw_event_id,
                event.source_id,
                event.dedup_group_id,
                event.title,
                event.normalized_title,
                event.summary,
                event.normalized_text,
                event.url,
                event.published_at,
                event.event_time,
                event.category,
                Jsonb(event.entities),
                Jsonb(event.topics),
                event.language,
                event.importance_score,
                event.urgency_score,
                event.novelty_score,
                event.source_reliability,
                event.status,
                Jsonb({}),
            ),
        ).fetchone()

    def set_dedup_group(self, conn: Connection, news_event_id: str, dedup_group_id: str) -> None:
        conn.execute(
            """
            UPDATE news_normalized_events
            SET dedup_group_id = %s, status = 'DEDUPED'
            WHERE news_event_id = %s
            """,
            (dedup_group_id, news_event_id),
        )

    def get_event(self, conn: Connection, news_event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM news_normalized_events WHERE news_event_id = %s", (news_event_id,)).fetchone()

    def list_recent(
        self,
        conn: Connection,
        *,
        limit: int = 100,
        category: str | None = None,
        source_id: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("category = %s")
            params.append(category)
        if source_id:
            clauses.append("source_id = %s")
            params.append(source_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(
            f"SELECT * FROM news_normalized_events {where} ORDER BY collected_at DESC, id DESC LIMIT %s",
            params,
        ).fetchall()

