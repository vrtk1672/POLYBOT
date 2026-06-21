from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class MarketFamilyRepository:
    def upsert_family(
        self,
        conn: Connection,
        *,
        market_id: str,
        market_family: str,
        category: str | None = None,
        subcategory: str | None = None,
        tags: list[str] | None = None,
        confidence: float = 0.0,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO market_family_map (
                market_id, market_family, category, subcategory, tags_json,
                confidence, reason, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id) DO UPDATE
            SET market_family = EXCLUDED.market_family,
                category = EXCLUDED.category,
                subcategory = EXCLUDED.subcategory,
                tags_json = EXCLUDED.tags_json,
                confidence = EXCLUDED.confidence,
                reason = EXCLUDED.reason,
                metadata_json = market_family_map.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            (market_id, market_family, category, subcategory, Jsonb(tags or []), confidence, reason, Jsonb(metadata or {})),
        ).fetchone()
        return row

    def list_families(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT market_family, category, COUNT(*) AS count, AVG(confidence) AS average_confidence
            FROM market_family_map
            GROUP BY market_family, category
            ORDER BY count DESC, market_family ASC
            """
        ).fetchall()
