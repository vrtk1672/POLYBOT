from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialSentimentScore


class SocialSentimentRepository:
    def insert_score(self, conn: Connection, score: SocialSentimentScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO social_sentiment_scores (
                sentiment_id, social_event_id, market_id, sentiment, sentiment_score,
                confidence, target, reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sentiment_id) DO NOTHING
            RETURNING *
            """,
            (score.sentiment_id, score.social_event_id, score.market_id, score.sentiment.value, score.sentiment_score, score.confidence, score.target, score.reason, Jsonb({})),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_sentiment_scores WHERE market_id = %s ORDER BY created_at DESC LIMIT %s", (market_id, limit)).fetchall()
