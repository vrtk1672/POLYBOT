from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleSource


class WhaleSourceRepository:
    def upsert_source(self, conn: Connection, source: WhaleSource) -> tuple[dict[str, Any], bool]:
        existing = self.get_source(conn, source.source_id)
        row = conn.execute(
            """
            INSERT INTO whale_sources (source_id, name, source_type, platform, url, enabled, reliability_score, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE
            SET name = EXCLUDED.name, source_type = EXCLUDED.source_type, platform = EXCLUDED.platform,
                url = EXCLUDED.url, enabled = EXCLUDED.enabled, reliability_score = EXCLUDED.reliability_score,
                metadata_json = whale_sources.metadata_json || EXCLUDED.metadata_json, updated_at = now()
            RETURNING *
            """,
            (source.source_id, source.name, source.source_type.value, source.platform, source.url, source.enabled, source.reliability_score, Jsonb(source.metadata)),
        ).fetchone()
        return row, existing is None

    def get_source(self, conn: Connection, source_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM whale_sources WHERE source_id = %s", (source_id,)).fetchone()

    def list_sources(self, conn: Connection, *, enabled: bool | None = None, source_type: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if enabled is not None:
            clauses.append("enabled = %s")
            params.append(enabled)
        if source_type:
            clauses.append("source_type = %s")
            params.append(source_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return conn.execute(f"SELECT * FROM whale_sources {where} ORDER BY source_id", params).fetchall()

    def set_enabled(self, conn: Connection, source_id: str, enabled: bool) -> None:
        conn.execute("UPDATE whale_sources SET enabled = %s, updated_at = now() WHERE source_id = %s", (enabled, source_id))

    def update_fetch_status(self, conn: Connection, source_id: str, *, success: bool, error_message: str | None = None) -> None:
        if success:
            conn.execute("UPDATE whale_sources SET last_fetch_at = now(), last_success_at = now(), updated_at = now() WHERE source_id = %s", (source_id,))
        else:
            conn.execute(
                "UPDATE whale_sources SET last_fetch_at = now(), last_error_at = now(), error_count = error_count + 1, metadata_json = metadata_json || %s, updated_at = now() WHERE source_id = %s",
                (Jsonb({"last_error": error_message or "unknown"}), source_id),
            )
