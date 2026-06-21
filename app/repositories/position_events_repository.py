from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.position_event import PositionEventContract


class PositionEventsRepository:
    def append(self, conn: Connection, event: PositionEventContract) -> None:
        conn.execute(
            """
            INSERT INTO position_events (
                id, position_id, event_type, event_at, reason, details
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.position_id,
                event.event_type,
                event.event_at,
                event.reason,
                Jsonb(event.details),
            ),
        )

    def list_for_position(self, conn: Connection, position_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM position_events
            WHERE position_id = %s
            ORDER BY event_at ASC, created_at ASC
            """,
            (position_id,),
        ).fetchall()
