from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.external_event_normalized import ExternalEventNormalizedContract


class ExternalEventsNormalizedRepository:
    def insert(self, conn: Connection, event: ExternalEventNormalizedContract) -> None:
        conn.execute(
            """
            INSERT INTO external_events_normalized (
                id, external_raw_event_id, intelligence_source_id, normalized_title,
                normalized_summary, published_at, canonical_url, canonical_hash,
                event_language, source_category, trust_weight_snapshot, dedupe_key,
                normalization_version, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.external_raw_event_id,
                event.intelligence_source_id,
                event.normalized_title,
                event.normalized_summary,
                event.published_at,
                event.canonical_url,
                event.canonical_hash,
                event.event_language,
                event.source_category,
                event.trust_weight_snapshot,
                event.dedupe_key,
                event.normalization_version,
                event.status,
                Jsonb(event.metadata_json),
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT normalized.*
            FROM external_events_normalized AS normalized
            JOIN external_raw_events AS raw
              ON raw.id = normalized.external_raw_event_id
            WHERE raw.intelligence_ingestion_run_id = %s
            ORDER BY normalized.created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def list_recent(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_events_normalized
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def get_by_id(self, conn: Connection, external_event_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM external_events_normalized
            WHERE id = %s
            LIMIT 1
            """,
            (external_event_id,),
        ).fetchone()

    def find_by_dedupe_key(self, conn: Connection, dedupe_key: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_events_normalized
            WHERE dedupe_key = %s
            ORDER BY created_at ASC
            """,
            (dedupe_key,),
        ).fetchall()

    def list_by_ingestion_run_id(self, conn: Connection, intelligence_ingestion_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT normalized.*
            FROM external_events_normalized AS normalized
            JOIN external_raw_events AS raw
              ON raw.id = normalized.external_raw_event_id
            WHERE raw.intelligence_ingestion_run_id = %s
            ORDER BY normalized.created_at ASC
            """,
            (intelligence_ingestion_run_id,),
        ).fetchall()
