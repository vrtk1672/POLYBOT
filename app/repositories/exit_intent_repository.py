from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.exit_cortex.contracts import ExitIntent


class ExitIntentRepository:
    def insert(self, conn: Connection, intent: ExitIntent) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO exit_intents (
                exit_intent_id, exit_plan_id, order_id, market_id, side, exit_side,
                reason, intent_status, exit_price_target, exit_size, exit_size_pct,
                max_slippage_bps, urgency, execution_mode, paper_shadow_only,
                risk_snapshot_json, liquidity_snapshot_json, trigger_snapshot_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                intent.exit_intent_id,
                intent.exit_plan_id,
                intent.order_id,
                intent.market_id,
                intent.side,
                intent.exit_side,
                intent.reason,
                intent.intent_status,
                intent.exit_price_target,
                intent.exit_size,
                intent.exit_size_pct,
                intent.max_slippage_bps,
                intent.urgency,
                intent.execution_mode,
                intent.paper_shadow_only,
                Jsonb(intent.risk_snapshot),
                Jsonb(intent.liquidity_snapshot),
                Jsonb(intent.trigger_snapshot),
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_intents ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_plan(self, conn: Connection, exit_plan_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_intents WHERE exit_plan_id=%s ORDER BY created_at DESC, id DESC", (exit_plan_id,)).fetchall()
