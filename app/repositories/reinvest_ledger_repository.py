from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class ReinvestLedgerRepository:
    def insert(
        self,
        conn: Connection,
        *,
        ledger_id: str,
        event_type: str,
        amount_usd: float,
        from_bucket: str | None,
        to_bucket: str | None,
        reason: str,
        policy: dict[str, Any],
        realized_profit_usd: float | None = None,
        source_allocation_id: str | None = None,
    ) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO reinvest_ledger (
                ledger_id, event_type, amount_usd, from_bucket, to_bucket, source_allocation_id,
                realized_profit_usd, reason, policy_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (ledger_id, event_type, amount_usd, from_bucket, to_bucket, source_allocation_id, realized_profit_usd, reason, Jsonb(policy)),
        ).fetchone()

    def recent(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM reinvest_ledger ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


