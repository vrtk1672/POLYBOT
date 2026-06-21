from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.news_neuron.contracts import NewsMarketLink


class NewsMarketLinkRepository:
    def insert_link(self, conn: Connection, link: NewsMarketLink) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO news_market_links (
                link_id, news_event_id, market_id, link_score, link_reason,
                direction, confidence, matched_entities_json, matched_terms_json,
                method, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (link_id) DO UPDATE
            SET link_score = EXCLUDED.link_score,
                link_reason = EXCLUDED.link_reason,
                direction = EXCLUDED.direction,
                confidence = EXCLUDED.confidence,
                matched_entities_json = EXCLUDED.matched_entities_json,
                matched_terms_json = EXCLUDED.matched_terms_json,
                method = EXCLUDED.method,
                metadata_json = news_market_links.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            (
                link.link_id,
                link.news_event_id,
                link.market_id,
                link.link_score,
                link.link_reason,
                link.direction.value,
                link.confidence,
                Jsonb(link.matched_entities),
                Jsonb(link.matched_terms),
                link.method,
                Jsonb({}),
            ),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT * FROM news_market_links
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

    def list_by_news(self, conn: Connection, news_event_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT * FROM news_market_links
            WHERE news_event_id = %s
            ORDER BY link_score DESC, id DESC
            LIMIT %s
            """,
            (news_event_id, limit),
        ).fetchall()
