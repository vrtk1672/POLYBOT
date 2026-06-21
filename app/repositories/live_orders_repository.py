from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.order import LiveOrderContract


class LiveOrdersRepository:
    def upsert(self, conn: Connection, order: LiveOrderContract) -> None:
        conn.execute(
            """
            INSERT INTO live_orders (
                id, client_order_id, cycle_id, decision_id, market_id, token_id,
                side, action, price, size, notional, status, exchange_status,
                exchange_order_id, raw_request, raw_response, error_text
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET client_order_id = EXCLUDED.client_order_id,
                cycle_id = EXCLUDED.cycle_id,
                decision_id = EXCLUDED.decision_id,
                market_id = EXCLUDED.market_id,
                token_id = EXCLUDED.token_id,
                side = EXCLUDED.side,
                action = EXCLUDED.action,
                price = EXCLUDED.price,
                size = EXCLUDED.size,
                notional = EXCLUDED.notional,
                status = EXCLUDED.status,
                exchange_status = EXCLUDED.exchange_status,
                exchange_order_id = EXCLUDED.exchange_order_id,
                raw_request = EXCLUDED.raw_request,
                raw_response = EXCLUDED.raw_response,
                error_text = EXCLUDED.error_text,
                updated_at = now()
            """,
            (
                order.id,
                order.client_order_id,
                order.cycle_id,
                order.decision_id,
                order.market_id,
                order.token_id,
                order.side,
                order.action,
                order.price,
                order.size,
                order.notional,
                order.status,
                order.exchange_status,
                order.exchange_order_id,
                Jsonb(order.raw_request),
                Jsonb(order.raw_response),
                order.error_text,
            ),
        )

    def get_by_id(self, conn: Connection, order_id: str) -> dict[str, object] | None:
        return conn.execute(
            "SELECT * FROM live_orders WHERE id = %s",
            (order_id,),
        ).fetchone()

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            "SELECT * FROM live_orders WHERE cycle_id = %s ORDER BY created_at ASC",
            (cycle_id,),
        ).fetchall()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM live_orders
            WHERE market_id = %s
            ORDER BY created_at ASC
            """,
            (market_id,),
        ).fetchall()
