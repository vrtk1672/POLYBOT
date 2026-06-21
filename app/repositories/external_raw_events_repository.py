from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.external_raw_event import ExternalRawEventContract


class ExternalRawEventsRepository:
    def insert(self, conn: Connection, event: ExternalRawEventContract) -> None:
        conn.execute(
            """
            INSERT INTO external_raw_events (
                id, intelligence_ingestion_run_id, intelligence_source_id, source_event_id,
                source_url, source_published_at, source_title, raw_content_text,
                raw_payload_json, raw_hash, fetched_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.intelligence_ingestion_run_id,
                event.intelligence_source_id,
                event.source_event_id,
                event.source_url,
                event.source_published_at,
                event.source_title,
                event.raw_content_text,
                Jsonb(event.raw_payload_json),
                event.raw_hash,
                event.fetched_at,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM external_raw_events
            WHERE intelligence_ingestion_run_id = %s
            ORDER BY fetched_at ASC, created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, raw_event_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM external_raw_events
            WHERE id = %s
            LIMIT 1
            """,
            (raw_event_id,),
        ).fetchone()
