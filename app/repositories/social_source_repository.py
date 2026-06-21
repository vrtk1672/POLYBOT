from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.social_neuron.contracts import SocialSource


class SocialSourceRepository:
    def upsert_source(self, conn: Connection, source: SocialSource) -> tuple[dict[str, Any], bool]:
        existing = self.get_source(conn, source.source_id)
        row = conn.execute(
            """
            INSERT INTO social_sources (
                source_id, name, source_type, platform, category, url, feed_url, enabled,
                reliability_score, noise_baseline, bot_risk_baseline, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE
            SET name = EXCLUDED.name,
                source_type = EXCLUDED.source_type,
                platform = EXCLUDED.platform,
                category = EXCLUDED.category,
                url = EXCLUDED.url,
                feed_url = EXCLUDED.feed_url,
                enabled = EXCLUDED.enabled,
                reliability_score = EXCLUDED.reliability_score,
                noise_baseline = EXCLUDED.noise_baseline,
                bot_risk_baseline = EXCLUDED.bot_risk_baseline,
                metadata_json = social_sources.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            (
                source.source_id,
                source.name,
                source.source_type.value,
                source.platform.value,
                source.category,
                source.url,
                source.feed_url,
                source.enabled,
                source.reliability_score,
                source.noise_baseline,
                source.bot_risk_baseline,
                Jsonb(source.metadata),
            ),
        ).fetchone()
        return row, existing is None

    def get_source(self, conn: Connection, source_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM social_sources WHERE source_id = %s", (source_id,)).fetchone()

    def list_sources(
        self,
        conn: Connection,
        *,
        enabled: bool | None = None,
        platform: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            clauses.append("enabled = %s")
            params.append(enabled)
        if platform:
            clauses.append("platform = %s")
            params.append(platform)
        if category:
            clauses.append("category = %s")
            params.append(category)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return conn.execute(f"SELECT * FROM social_sources {where} ORDER BY category NULLS LAST, source_id", params).fetchall()

    def set_enabled(self, conn: Connection, source_id: str, enabled: bool) -> None:
        conn.execute("UPDATE social_sources SET enabled = %s, updated_at = now() WHERE source_id = %s", (enabled, source_id))

    def update_fetch_status(self, conn: Connection, source_id: str, *, success: bool, error_message: str | None = None) -> None:
        if success:
            conn.execute(
                """
                UPDATE social_sources
                SET last_fetch_at = now(), last_success_at = now(), updated_at = now()
                WHERE source_id = %s
                """,
                (source_id,),
            )
            return
        conn.execute(
            """
            UPDATE social_sources
            SET last_fetch_at = now(), last_error_at = now(), error_count = error_count + 1,
                metadata_json = metadata_json || %s, updated_at = now()
            WHERE source_id = %s
            """,
            (Jsonb({"last_error": error_message or "unknown"}), source_id),
        )
