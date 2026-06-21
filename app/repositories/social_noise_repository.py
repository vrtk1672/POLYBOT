from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialNoiseScore


class SocialNoiseRepository:
    def insert_score(self, conn: Connection, score: SocialNoiseScore) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO social_noise_scores (
                noise_id, social_event_id, market_id, platform, spam_score, bot_risk,
                duplicate_risk, coordinated_activity_risk, noise_score, reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (noise_id) DO NOTHING
            RETURNING *
            """,
            (score.noise_id, score.social_event_id, score.market_id, score.platform.value if score.platform else None, score.spam_score, score.bot_risk, score.duplicate_risk, score.coordinated_activity_risk, score.noise_score, score.reason, Jsonb({})),
        ).fetchone()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_noise_scores WHERE market_id = %s ORDER BY created_at DESC LIMIT %s", (market_id, limit)).fetchall()
