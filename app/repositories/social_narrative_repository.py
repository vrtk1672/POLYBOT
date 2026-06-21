from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialNarrative


class SocialNarrativeRepository:
    def upsert_narrative(self, conn: Connection, narrative: SocialNarrative) -> dict[str, Any]:
        existing = conn.execute("SELECT * FROM social_narratives WHERE narrative_key = %s", (narrative.narrative_key,)).fetchone()
        if existing:
            return conn.execute(
                """
                UPDATE social_narratives
                SET last_seen_at = now(),
                    event_count = event_count + 1,
                    narrative_strength = LEAST(1, GREATEST(narrative_strength, %s)),
                    confidence = LEAST(1, GREATEST(confidence, %s)),
                    market_ids_json = %s,
                    metadata_json = metadata_json || %s
                WHERE narrative_key = %s
                RETURNING *
                """,
                (narrative.narrative_strength, narrative.confidence, Jsonb(narrative.market_ids), Jsonb({}), narrative.narrative_key),
            ).fetchone()
        return conn.execute(
            """
            INSERT INTO social_narratives (
                narrative_id, narrative_key, title, topics_json, entities_json, market_ids_json,
                event_count, narrative_strength, confidence, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (narrative.narrative_id, narrative.narrative_key, narrative.title, Jsonb(narrative.topics), Jsonb(narrative.entities), Jsonb(narrative.market_ids), max(1, narrative.event_count), narrative.narrative_strength, narrative.confidence, narrative.status, Jsonb({})),
        ).fetchone()

    def list_narratives(self, conn: Connection, *, status: str | None = "ACTIVE", limit: int = 100) -> list[dict[str, Any]]:
        if status:
            return conn.execute("SELECT * FROM social_narratives WHERE status = %s ORDER BY narrative_strength DESC, last_seen_at DESC LIMIT %s", (status, limit)).fetchall()
        return conn.execute("SELECT * FROM social_narratives ORDER BY narrative_strength DESC, last_seen_at DESC LIMIT %s", (limit,)).fetchall()

    def list_by_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM social_narratives WHERE market_ids_json ? %s ORDER BY last_seen_at DESC LIMIT %s", (market_id, limit)).fetchall()
