from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.position import PositionContract


class PositionsRepository:
    def upsert(self, conn: Connection, position: PositionContract) -> None:
        conn.execute(
            """
            INSERT INTO positions (
                id, market_id, side, size, avg_entry, current_status, unrealized,
                realized, thesis_state, invalidation_state, opened_at, updated_at, closed_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                size = EXCLUDED.size,
                avg_entry = EXCLUDED.avg_entry,
                current_status = EXCLUDED.current_status,
                unrealized = EXCLUDED.unrealized,
                realized = EXCLUDED.realized,
                thesis_state = EXCLUDED.thesis_state,
                invalidation_state = EXCLUDED.invalidation_state,
                opened_at = EXCLUDED.opened_at,
                updated_at = EXCLUDED.updated_at,
                closed_at = EXCLUDED.closed_at
            """,
            (
                position.id,
                position.market_id,
                position.side,
                position.size,
                position.avg_entry,
                position.current_status,
                position.unrealized,
                position.realized,
                position.thesis_state,
                position.invalidation_state,
                position.opened_at,
                position.updated_at,
                position.closed_at,
            ),
        )

    def get_open_position(
        self,
        conn: Connection,
        *,
        market_id: str,
        side: str,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM positions
            WHERE market_id = %s
              AND side = %s
              AND closed_at IS NULL
            ORDER BY opened_at ASC
            LIMIT 1
            """,
            (market_id, side),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM positions
            WHERE market_id = %s
            ORDER BY opened_at ASC
            """,
            (market_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, position_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM positions
            WHERE id = %s
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()
