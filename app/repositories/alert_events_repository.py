from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.alert_event import AlertEventContract


class AlertEventsRepository:
    def insert(self, conn: Connection, alert: AlertEventContract) -> None:
        conn.execute(
            """
            INSERT INTO alert_events (
                id, event_class, severity_class, title, body_text,
                dedupe_key, source_ref, delivery_status_class, payload_json, delivered_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                alert.id,
                alert.event_class,
                alert.severity_class,
                alert.title,
                alert.body_text,
                alert.dedupe_key,
                alert.source_ref,
                alert.delivery_status_class,
                Jsonb(alert.payload_json),
                alert.delivered_at,
            ),
        )

    def list_recent(self, conn: Connection, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM alert_events
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def get_recent_by_dedupe_key(
        self,
        conn: Connection,
        *,
        dedupe_key: str,
        since: datetime,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM alert_events
            WHERE dedupe_key = %s
              AND created_at >= %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (dedupe_key, since),
        ).fetchone()
