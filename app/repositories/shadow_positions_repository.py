from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.shadow_position import ShadowPositionContract


class ShadowPositionsRepository:
    def upsert(self, conn: Connection, position: ShadowPositionContract) -> None:
        conn.execute(
            """
            INSERT INTO shadow_positions (
                id, shadow_run_id, shadow_order_id, market_id, intended_outcome, size, avg_entry,
                current_status, mark_price, unrealized, realized, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, payload_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET shadow_run_id = EXCLUDED.shadow_run_id,
                shadow_order_id = EXCLUDED.shadow_order_id,
                market_id = EXCLUDED.market_id,
                intended_outcome = EXCLUDED.intended_outcome,
                size = EXCLUDED.size,
                avg_entry = EXCLUDED.avg_entry,
                current_status = EXCLUDED.current_status,
                mark_price = EXCLUDED.mark_price,
                unrealized = EXCLUDED.unrealized,
                realized = EXCLUDED.realized,
                thesis_state = EXCLUDED.thesis_state,
                invalidation_state = EXCLUDED.invalidation_state,
                opened_at = EXCLUDED.opened_at,
                updated_at = EXCLUDED.updated_at,
                closed_at = EXCLUDED.closed_at,
                payload_json = EXCLUDED.payload_json
            """,
            (
                position.id,
                position.shadow_run_id,
                position.shadow_order_id,
                position.market_id,
                position.intended_outcome,
                position.size,
                position.avg_entry,
                position.current_status,
                position.mark_price,
                position.unrealized,
                position.realized,
                position.thesis_state,
                position.invalidation_state,
                position.opened_at,
                position.updated_at,
                position.closed_at,
                Jsonb(position.payload_json),
            ),
        )

    def get_by_id(self, conn: Connection, shadow_position_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM shadow_positions
            WHERE id = %s
            LIMIT 1
            """,
            (shadow_position_id,),
        ).fetchone()

    def list_for_run(self, conn: Connection, shadow_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_positions
            WHERE shadow_run_id = %s
            ORDER BY updated_at DESC, market_id ASC
            """,
            (shadow_run_id,),
        ).fetchall()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_positions
            WHERE market_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()
