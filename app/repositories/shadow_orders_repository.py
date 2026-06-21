from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.shadow_order import ShadowOrderContract


class ShadowOrdersRepository:
    def upsert(self, conn: Connection, order: ShadowOrderContract) -> None:
        conn.execute(
            """
            INSERT INTO shadow_orders (
                id, shadow_run_id, cycle_id, decision_id, market_id, token_id,
                intended_outcome, action, intended_price, intended_size, notional,
                guard_result, execution_policy_result, status,
                raw_intent_json, raw_guard_json, raw_policy_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (id) DO UPDATE
            SET shadow_run_id = EXCLUDED.shadow_run_id,
                cycle_id = EXCLUDED.cycle_id,
                decision_id = EXCLUDED.decision_id,
                market_id = EXCLUDED.market_id,
                token_id = EXCLUDED.token_id,
                intended_outcome = EXCLUDED.intended_outcome,
                action = EXCLUDED.action,
                intended_price = EXCLUDED.intended_price,
                intended_size = EXCLUDED.intended_size,
                notional = EXCLUDED.notional,
                guard_result = EXCLUDED.guard_result,
                execution_policy_result = EXCLUDED.execution_policy_result,
                status = EXCLUDED.status,
                raw_intent_json = EXCLUDED.raw_intent_json,
                raw_guard_json = EXCLUDED.raw_guard_json,
                raw_policy_json = EXCLUDED.raw_policy_json,
                updated_at = now()
            """,
            (
                order.id,
                order.shadow_run_id,
                order.cycle_id,
                order.decision_id,
                order.market_id,
                order.token_id,
                order.intended_outcome,
                order.action,
                order.intended_price,
                order.intended_size,
                order.notional,
                order.guard_result,
                order.execution_policy_result,
                order.status,
                Jsonb(order.raw_intent_json),
                Jsonb(order.raw_guard_json),
                Jsonb(order.raw_policy_json),
            ),
        )

    def list_for_run(self, conn: Connection, shadow_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_orders
            WHERE shadow_run_id = %s
            ORDER BY created_at ASC, market_id ASC
            """,
            (shadow_run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, shadow_order_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM shadow_orders
            WHERE id = %s
            LIMIT 1
            """,
            (shadow_order_id,),
        ).fetchone()

    def list_for_market(self, conn: Connection, market_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM shadow_orders
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (market_id,),
        ).fetchall()
