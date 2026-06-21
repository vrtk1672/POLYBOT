from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.news_neuron.contracts import DedupGroup


class NewsDedupRepository:
    def get_by_group_hash(self, conn: Connection, group_hash: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM news_dedup_groups WHERE group_hash = %s LIMIT 1", (group_hash,)).fetchone()

    def upsert_group(self, conn: Connection, group: DedupGroup) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_dedup_groups (
                dedup_group_id, canonical_news_event_id, group_hash, normalized_title,
                topic_signature, event_count, sources_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedup_group_id) DO UPDATE
            SET last_seen_at = now(),
                event_count = news_dedup_groups.event_count + 1,
                sources_json = EXCLUDED.sources_json,
                metadata_json = news_dedup_groups.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                group.dedup_group_id,
                group.canonical_news_event_id,
                group.group_hash,
                group.topic_signature,
                group.topic_signature,
                group.event_count,
                Jsonb(group.sources),
                Jsonb({}),
            ),
        ).fetchone()

    def increment_group(self, conn: Connection, dedup_group_id: str, sources: list[str]) -> dict[str, Any]:
        return conn.execute(
            """
            UPDATE news_dedup_groups
            SET event_count = event_count + 1,
                last_seen_at = now(),
                sources_json = %s
            WHERE dedup_group_id = %s
            RETURNING *
            """,
            (Jsonb(sources), dedup_group_id),
        ).fetchone()

