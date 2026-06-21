from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.order_status_event import OrderStatusEventContract


class OrderStatusHistoryRepository:
    def append(self, conn: Connection, event: OrderStatusEventContract) -> bool:
        last_row = conn.execute(
            """
            SELECT new_status, source, exchange_status, reason
            FROM order_status_history
            WHERE order_id = %s
            ORDER BY event_at DESC, created_at DESC
            LIMIT 1
            """,
            (event.order_id,),
        ).fetchone()
        if last_row and (
            str(last_row["new_status"]) == event.new_status
            and str(last_row["source"]) == event.source
            and (last_row["exchange_status"] or None) == event.exchange_status
            and (last_row["reason"] or None) == event.reason
        ):
            return False

        conn.execute(
            """
            INSERT INTO order_status_history (
                id, order_id, event_at, old_status, new_status, source,
                reason, exchange_status, raw_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.id,
                event.order_id,
                event.event_at,
                event.old_status,
                event.new_status,
                event.source,
                event.reason,
                event.exchange_status,
                Jsonb(event.raw_payload),
            ),
        )
        return True

    def list_for_order(self, conn: Connection, order_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM order_status_history
            WHERE order_id = %s
            ORDER BY event_at ASC, created_at ASC
            """,
            (order_id,),
        ).fetchall()
