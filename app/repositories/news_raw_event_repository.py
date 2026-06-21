from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.news_neuron.contracts import RawNewsEvent


class NewsRawEventRepository:
    def insert_raw_event(self, conn: Connection, event: RawNewsEvent) -> tuple[dict[str, Any], bool]:
        existing = self.get_by_content_hash(conn, event.content_hash)
        if existing:
            return existing, False
        row = conn.execute(
            """
            INSERT INTO news_raw_events (
                raw_event_id, source_id, external_id, url, title, summary, body_text,
                author, published_at, collected_at, language, raw_payload_json,
                content_hash, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (raw_event_id) DO UPDATE
            SET metadata_json = news_raw_events.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                event.raw_event_id,
                event.source_id,
                event.external_id,
                event.url,
                event.title,
                event.summary,
                event.body_text,
                event.author,
                event.published_at,
                event.collected_at,
                event.language,
                Jsonb(event.raw_payload),
                event.content_hash,
                Jsonb({}),
            ),
        ).fetchone()
        return row, True

    def get_by_content_hash(self, conn: Connection, content_hash: str) -> dict[str, Any] | None:
        return conn.execute(
            "SELECT * FROM news_raw_events WHERE content_hash = %s ORDER BY collected_at ASC LIMIT 1",
            (content_hash,),
        ).fetchone()

    def get_raw_event(self, conn: Connection, raw_event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM news_raw_events WHERE raw_event_id = %s", (raw_event_id,)).fetchone()

