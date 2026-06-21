from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.paper_order import PaperOrderContract
from app.services.paper_session import active_paper_session_id


class PaperOrdersRepository:
    def upsert(self, conn: Connection, order: PaperOrderContract) -> None:
        paper_session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, cycle_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status, fill_ratio,
                filled_size, remaining_size, avg_fill_price, min_size_check_passed, stale_at,
                payload_json, paper_session_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET paper_run_id = EXCLUDED.paper_run_id,
                paper_signal_id = EXCLUDED.paper_signal_id,
                cycle_id = EXCLUDED.cycle_id,
                market_id = EXCLUDED.market_id,
                intended_outcome = EXCLUDED.intended_outcome,
                action = EXCLUDED.action,
                intended_price = EXCLUDED.intended_price,
                intended_size = EXCLUDED.intended_size,
                notional = EXCLUDED.notional,
                status = EXCLUDED.status,
                fill_ratio = EXCLUDED.fill_ratio,
                filled_size = EXCLUDED.filled_size,
                remaining_size = EXCLUDED.remaining_size,
                avg_fill_price = EXCLUDED.avg_fill_price,
                min_size_check_passed = EXCLUDED.min_size_check_passed,
                stale_at = EXCLUDED.stale_at,
                payload_json = EXCLUDED.payload_json,
                paper_session_id = COALESCE(paper_orders.paper_session_id, EXCLUDED.paper_session_id),
                updated_at = now()
            """,
            (
                order.id,
                order.paper_run_id,
                order.paper_signal_id,
                order.cycle_id,
                order.market_id,
                order.intended_outcome,
                order.action,
                order.intended_price,
                order.intended_size,
                order.notional,
                order.status,
                order.fill_ratio,
                order.filled_size,
                order.remaining_size,
                order.avg_fill_price,
                order.min_size_check_passed,
                order.stale_at,
                Jsonb(order.payload_json),
                paper_session_id,
            ),
        )

    def list_for_run(self, conn: Connection, paper_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_orders
            WHERE paper_run_id = %s
            ORDER BY created_at ASC, market_id ASC
            """,
            (paper_run_id,),
        ).fetchall()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_orders
            WHERE market_id = %s
            ORDER BY created_at ASC
            """,
            (market_id,),
        ).fetchall()

    def list_open_for_run(self, conn: Connection, paper_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_orders
            WHERE paper_run_id = %s
              AND status IN ('OPEN', 'PARTIALLY_FILLED')
            ORDER BY created_at ASC
            """,
            (paper_run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, paper_order_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM paper_orders
            WHERE id = %s
            LIMIT 1
            """,
            (paper_order_id,),
        ).fetchone()
