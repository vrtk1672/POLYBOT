from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.paper_position import PaperPositionContract
from app.services.paper_session import active_paper_session_id


class PaperPositionsRepository:
    def upsert(self, conn: Connection, position: PaperPositionContract) -> None:
        paper_session_id = active_paper_session_id(conn) or "NO_ACTIVE_PAPER_SESSION"
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry, mark_price,
                unrealized, realized, current_status, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, payload_json, paper_session_id
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET paper_run_id = EXCLUDED.paper_run_id,
                market_id = EXCLUDED.market_id,
                intended_outcome = EXCLUDED.intended_outcome,
                size = EXCLUDED.size,
                avg_entry = EXCLUDED.avg_entry,
                mark_price = EXCLUDED.mark_price,
                unrealized = EXCLUDED.unrealized,
                realized = EXCLUDED.realized,
                current_status = EXCLUDED.current_status,
                thesis_state = EXCLUDED.thesis_state,
                invalidation_state = EXCLUDED.invalidation_state,
                opened_at = EXCLUDED.opened_at,
                updated_at = EXCLUDED.updated_at,
                closed_at = EXCLUDED.closed_at,
                payload_json = EXCLUDED.payload_json,
                paper_session_id = COALESCE(paper_positions.paper_session_id, EXCLUDED.paper_session_id)
            """,
            (
                position.id,
                position.paper_run_id,
                position.market_id,
                position.intended_outcome,
                position.size,
                position.avg_entry,
                position.mark_price,
                position.unrealized,
                position.realized,
                position.current_status,
                position.thesis_state,
                position.invalidation_state,
                position.opened_at,
                position.updated_at,
                position.closed_at,
                Jsonb(position.payload_json),
                paper_session_id,
            ),
        )

    def get_open_position(
        self,
        conn: Connection,
        *,
        paper_run_id: str,
        market_id: str,
        intended_outcome: str,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE paper_run_id = %s
              AND market_id = %s
              AND intended_outcome = %s
              AND closed_at IS NULL
            ORDER BY opened_at ASC
            LIMIT 1
            """,
            (paper_run_id, market_id, intended_outcome),
        ).fetchone()

    def get_by_id(self, conn: Connection, paper_position_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE id = %s
            LIMIT 1
            """,
            (paper_position_id,),
        ).fetchone()

    def list_open_for_run(self, conn: Connection, paper_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE paper_run_id = %s
              AND closed_at IS NULL
            ORDER BY updated_at DESC, market_id ASC
            """,
            (paper_run_id,),
        ).fetchall()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE market_id = %s
            ORDER BY updated_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()
