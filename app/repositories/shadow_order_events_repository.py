from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.shadow_order_event import ShadowOrderEventContract


class ShadowOrderEventsRepository:
    def append(self, conn: Connection, event: ShadowOrderEventContract) -> None:
        conn.execute(
            """
            INSERT INTO shadow_order_events (
                id, shadow_order_id, event_at, old_status, new_status, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.shadow_order_id,
                event.event_at,
                event.old_status,
                event.new_status,
                event.reason_code,
                event.reason_text,
                Jsonb(event.payload_json),
            ),
        )

    def list_for_order(self, conn: Connection, shadow_order_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_order_events
            WHERE shadow_order_id = %s
            ORDER BY event_at ASC, created_at ASC
            """,
            (shadow_order_id,),
        ).fetchall()
