from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.shadow_position_event import ShadowPositionEventContract


class ShadowPositionEventsRepository:
    def append(self, conn: Connection, event: ShadowPositionEventContract) -> None:
        conn.execute(
            """
            INSERT INTO shadow_position_events (
                id, shadow_position_id, event_at, event_type, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.shadow_position_id,
                event.event_at,
                event.event_type,
                event.reason_code,
                event.reason_text,
                Jsonb(event.payload_json),
            ),
        )

    def list_for_position(self, conn: Connection, shadow_position_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_position_events
            WHERE shadow_position_id = %s
            ORDER BY event_at ASC, created_at ASC
            """,
            (shadow_position_id,),
        ).fetchall()
