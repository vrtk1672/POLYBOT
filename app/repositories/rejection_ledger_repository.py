from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.rejection import RejectionLedgerContract


class RejectionLedgerRepository:
    def upsert_many(
        self,
        conn: Connection,
        rejections: list[RejectionLedgerContract],
    ) -> None:
        for rejection in rejections:
            conn.execute(
                """
                INSERT INTO rejection_ledger (
                    id, cycle_id, market_id, stage, reason_code, reason_text, payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (cycle_id, market_id, stage, reason_code) DO UPDATE
                SET reason_text = EXCLUDED.reason_text,
                    payload = EXCLUDED.payload
                """,
                (
                    rejection.id,
                    rejection.cycle_id,
                    rejection.market_id,
                    rejection.stage,
                    rejection.reason_code,
                    rejection.reason_text,
                    Jsonb(rejection.payload),
                ),
            )

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM rejection_ledger
            WHERE cycle_id = %s
            ORDER BY created_at ASC, market_id ASC
            """,
            (cycle_id,),
        ).fetchall()

    def list_for_cycle_market(
        self,
        conn: Connection,
        *,
        cycle_id: str,
        market_id: str,
    ) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM rejection_ledger
            WHERE cycle_id = %s
              AND market_id = %s
            ORDER BY created_at ASC
            """,
            (cycle_id, market_id),
        ).fetchall()
