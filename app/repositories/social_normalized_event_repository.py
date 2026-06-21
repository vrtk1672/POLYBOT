from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import NormalizedSocialEvent


class SocialNormalizedEventRepository:
    def upsert_event(self, conn: Connection, event: NormalizedSocialEvent) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO social_normalized_events (
                social_event_id, raw_social_event_id, source_id, platform, dedup_group_id,
                text, normalized_text, author_handle, url, published_at, category,
                entities_json, topics_json, hashtags_json, cashtags_json, language,
                engagement_score, influence_score, spam_score, bot_risk, novelty_score, status,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (social_event_id) DO UPDATE
            SET dedup_group_id = EXCLUDED.dedup_group_id,
                spam_score = EXCLUDED.spam_score,
                bot_risk = EXCLUDED.bot_risk,
                novelty_score = EXCLUDED.novelty_score,
                status = EXCLUDED.status,
                metadata_json = social_normalized_events.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            (
                event.social_event_id,
                event.raw_social_event_id,
                event.source_id,
                event.platform.value,
                event.dedup_group_id,
                event.text,
                event.normalized_text,
                event.author_handle,
                event.url,
                event.published_at,
                event.category,
                Jsonb(event.entities),
                Jsonb(event.topics),
                Jsonb(event.hashtags),
                Jsonb(event.cashtags),
                event.language,
                event.engagement_score,
                event.influence_score,
                event.spam_score,
                event.bot_risk,
                event.novelty_score,
                event.status,
                Jsonb({}),
            ),
        ).fetchone()

    def set_dedup_group(self, conn: Connection, social_event_id: str, dedup_group_id: str) -> None:
        conn.execute("UPDATE social_normalized_events SET dedup_group_id = %s, status = 'DEDUPED' WHERE social_event_id = %s", (dedup_group_id, social_event_id))

    def mark_linked(self, conn: Connection, social_event_id: str) -> None:
        conn.execute("UPDATE social_normalized_events SET status = 'LINKED' WHERE social_event_id = %s", (social_event_id,))

    def get_event(self, conn: Connection, social_event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM social_normalized_events WHERE social_event_id = %s", (social_event_id,)).fetchone()

    def list_recent(self, conn: Connection, *, limit: int = 100, platform: str | None = None, category: str | None = None, source_id: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if platform:
            clauses.append("platform = %s")
            params.append(platform)
        if category:
            clauses.append("category = %s")
            params.append(category)
        if source_id:
            clauses.append("source_id = %s")
            params.append(source_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM social_normalized_events {where} ORDER BY collected_at DESC, id DESC LIMIT %s", params).fetchall()

    def list_for_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT e.*
            FROM social_normalized_events e
            JOIN social_market_links l ON l.social_event_id = e.social_event_id
            WHERE l.market_id = %s
            ORDER BY e.collected_at DESC, e.id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()
