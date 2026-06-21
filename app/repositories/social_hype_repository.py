from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialHypeScore


class SocialHypeRepository:
    def insert_score(self, conn: Connection, score: SocialHypeScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO social_hype_scores (
                hype_id, market_id, window_seconds, mention_count, unique_author_count,
                mentions_velocity, velocity_zscore, hype_pressure, sentiment, sentiment_confidence,
                bot_risk, spam_ratio, narrative_strength, confidence, signal_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hype_id) DO NOTHING
            RETURNING *
            """,
            (
                score.hype_id,
                score.market_id,
                score.window_seconds,
                score.mention_count,
                score.unique_author_count,
                score.mentions_velocity,
                score.velocity_zscore,
                score.hype_pressure,
                score.sentiment.value,
                score.sentiment_confidence,
                score.bot_risk,
                score.spam_ratio,
                score.narrative_strength,
                score.confidence,
                Jsonb(score.signal),
                Jsonb({}),
            ),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_hype_scores WHERE market_id = %s ORDER BY computed_at DESC LIMIT %s", (market_id, limit)).fetchall()

    def list_top(self, conn: Connection, *, limit: int = 50, min_hype: float | None = None, min_confidence: float | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if min_hype is not None:
            clauses.append("hype_pressure >= %s")
            params.append(min_hype)
        if min_confidence is not None:
            clauses.append("confidence >= %s")
            params.append(min_confidence)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM social_hype_scores {where} ORDER BY hype_pressure DESC, computed_at DESC LIMIT %s", params).fetchall()
