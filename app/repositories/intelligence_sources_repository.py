from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.intelligence_source import IntelligenceSourceContract


class IntelligenceSourcesRepository:
    def upsert(self, conn: Connection, source: IntelligenceSourceContract) -> None:
        conn.execute(
            """
            INSERT INTO intelligence_sources (
                id, source_key, source_name, source_type, base_url, category,
                trust_weight, latency_score, noise_score, relevance_scope,
                is_enabled, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_key) DO UPDATE
            SET source_name = EXCLUDED.source_name,
                source_type = EXCLUDED.source_type,
                base_url = EXCLUDED.base_url,
                category = EXCLUDED.category,
                trust_weight = EXCLUDED.trust_weight,
                latency_score = EXCLUDED.latency_score,
                noise_score = EXCLUDED.noise_score,
                relevance_scope = EXCLUDED.relevance_scope,
                is_enabled = EXCLUDED.is_enabled,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (
                source.id,
                source.source_key,
                source.source_name,
                source.source_type,
                source.base_url,
                source.category,
                source.trust_weight,
                source.latency_score,
                source.noise_score,
                source.relevance_scope,
                source.is_enabled,
                Jsonb(source.metadata_json),
            ),
        )

    def list_all(self, conn: Connection) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_sources
            ORDER BY source_name ASC
            """
        ).fetchall()

    def list_enabled(self, conn: Connection) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_sources
            WHERE is_enabled = true
            ORDER BY source_name ASC
            """
        ).fetchall()

    def get_by_id(self, conn: Connection, source_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_sources
            WHERE id = %s
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()

    def get_by_key(self, conn: Connection, source_key: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM intelligence_sources
            WHERE source_key = %s
            LIMIT 1
            """,
            (source_key,),
        ).fetchone()
