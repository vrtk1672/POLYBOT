from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialMarketLink


class SocialMarketLinkRepository:
    def insert_link(self, conn: Connection, link: SocialMarketLink) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO social_market_links (
                social_link_id, social_event_id, market_id, link_score, link_reason,
                sentiment_direction, confidence, matched_entities_json, matched_terms_json,
                method, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (social_link_id) DO NOTHING
            RETURNING *
            """,
            (
                link.social_link_id,
                link.social_event_id,
                link.market_id,
                link.link_score,
                link.link_reason,
                link.sentiment_direction.value,
                link.confidence,
                Jsonb(link.matched_entities),
                Jsonb(link.matched_terms),
                link.method,
                Jsonb({}),
            ),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_market_links WHERE market_id = %s ORDER BY created_at DESC, id DESC LIMIT %s", (market_id, limit)).fetchall()

    def list_by_social_event(self, conn: Connection, social_event_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_market_links WHERE social_event_id = %s ORDER BY link_score DESC LIMIT %s", (social_event_id, limit)).fetchall()
