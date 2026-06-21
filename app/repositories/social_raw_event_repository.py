from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import RawSocialEvent


class SocialRawEventRepository:
    def insert_event(self, conn: Connection, event: RawSocialEvent) -> tuple[dict[str, Any], bool]:
        existing = conn.execute("SELECT * FROM social_raw_events WHERE content_hash = %s", (event.content_hash,)).fetchone()
        if existing:
            return existing, False
        row = conn.execute(
            """
            INSERT INTO social_raw_events (
                raw_social_event_id, source_id, platform, external_id, url, author_id, author_handle,
                text, raw_text, published_at, collected_at, language, engagement_json,
                raw_payload_json, content_hash, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                event.raw_social_event_id,
                event.source_id,
                event.platform.value,
                event.external_id,
                event.url,
                event.author_id,
                event.author_handle,
                event.text,
                event.raw_text,
                event.published_at,
                event.collected_at,
                event.language,
                Jsonb(event.engagement),
                Jsonb(event.raw_payload),
                event.content_hash,
                Jsonb({}),
            ),
        ).fetchone()
        return row, True

    def get_event(self, conn: Connection, raw_social_event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM social_raw_events WHERE raw_social_event_id = %s", (raw_social_event_id,)).fetchone()
