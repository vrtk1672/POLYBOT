from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class EventConsumerRepository:
    def register_consumer(
        self,
        conn: Connection,
        *,
        consumer_name: str,
        event_types: list[str],
        group: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO event_consumers (
                consumer_name, consumer_group, subscribed_event_types, status, metadata_json
            )
            VALUES (%s, %s, %s, 'ACTIVE', %s)
            ON CONFLICT (consumer_name) DO UPDATE
            SET consumer_group = EXCLUDED.consumer_group,
                subscribed_event_types = EXCLUDED.subscribed_event_types,
                status = CASE WHEN event_consumers.status = 'DISABLED' THEN 'DISABLED' ELSE 'ACTIVE' END,
                metadata_json = event_consumers.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            """,
            (consumer_name, group, event_types, Jsonb(metadata or {})),
        )

    def list_consumers(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM event_consumers
            ORDER BY consumer_name ASC
            """
        ).fetchall()

    def get_consumer(self, conn: Connection, consumer_name: str) -> dict[str, Any] | None:
        return conn.execute(
            "SELECT * FROM event_consumers WHERE consumer_name = %s",
            (consumer_name,),
        ).fetchone()

    def get_consumers_for_event_type(self, conn: Connection, event_type: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM event_consumers
            WHERE %s = ANY(subscribed_event_types)
              AND status = 'ACTIVE'
            ORDER BY consumer_name ASC
            """,
            (event_type,),
        ).fetchall()

    def mark_seen(self, conn: Connection, consumer_name: str, event_id: str | None = None) -> None:
        conn.execute(
            """
            UPDATE event_consumers
            SET last_seen_at = now(),
                last_event_id = COALESCE(%s, last_event_id),
                updated_at = now()
            WHERE consumer_name = %s
            """,
            (event_id, consumer_name),
        )

    def mark_success(self, conn: Connection, consumer_name: str, event_id: str) -> None:
        conn.execute(
            """
            UPDATE event_consumers
            SET status = 'ACTIVE',
                last_seen_at = now(),
                last_success_at = now(),
                last_event_id = %s,
                updated_at = now()
            WHERE consumer_name = %s
            """,
            (event_id, consumer_name),
        )

    def mark_error(self, conn: Connection, consumer_name: str, event_id: str | None = None) -> None:
        conn.execute(
            """
            UPDATE event_consumers
            SET status = 'ERROR',
                last_seen_at = now(),
                last_error_at = now(),
                last_event_id = COALESCE(%s, last_event_id),
                error_count = error_count + 1,
                updated_at = now()
            WHERE consumer_name = %s
            """,
            (event_id, consumer_name),
        )

    def pause_consumer(self, conn: Connection, consumer_name: str) -> None:
        conn.execute(
            "UPDATE event_consumers SET status = 'PAUSED', updated_at = now() WHERE consumer_name = %s",
            (consumer_name,),
        )

    def resume_consumer(self, conn: Connection, consumer_name: str) -> None:
        conn.execute(
            "UPDATE event_consumers SET status = 'ACTIVE', updated_at = now() WHERE consumer_name = %s",
            (consumer_name,),
        )
