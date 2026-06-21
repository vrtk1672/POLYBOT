from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.exit_cortex.contracts import ExitPlan


class ExitPlanRepository:
    def insert(self, conn: Connection, plan: ExitPlan) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, market_family, side, engine, strategy_route_id,
                allocation_id, risk_gate_run_id, order_id, position_ref, entry_price,
                entry_size, target_exit, partial_take_profit, partial_take_profit_pct,
                stop_loss, max_hold_seconds, invalidation_rule_json,
                liquidity_exit_check_json, emergency_exit_json,
                momentum_decay_exit_json, spread_exit_json, news_invalidated_exit_json,
                exit_mode, plan_status, created_from, data_confidence,
                insufficient_data, insufficient_data_reasons_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (exit_plan_id) DO UPDATE SET
                plan_status=EXCLUDED.plan_status,
                updated_at=now()
            RETURNING *
            """,
            (
                plan.exit_plan_id,
                plan.market_id,
                plan.market_family,
                plan.side,
                plan.engine,
                plan.strategy_route_id,
                plan.allocation_id,
                plan.risk_gate_run_id,
                plan.order_id,
                plan.position_ref,
                plan.entry_price,
                plan.entry_size,
                plan.target_exit,
                plan.partial_take_profit,
                plan.partial_take_profit_pct,
                plan.stop_loss,
                plan.max_hold_seconds,
                Jsonb(plan.invalidation_rule),
                Jsonb(plan.liquidity_exit_check),
                Jsonb(plan.emergency_exit),
                Jsonb(plan.momentum_decay_exit),
                Jsonb(plan.spread_exit),
                Jsonb(plan.news_invalidated_exit),
                plan.exit_mode,
                plan.plan_status,
                plan.created_from,
                plan.data_confidence,
                plan.insufficient_data,
                Jsonb(plan.insufficient_data_reasons),
            ),
        ).fetchone()

    def by_exit_plan_id(self, conn: Connection, exit_plan_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM exit_plans WHERE exit_plan_id=%s LIMIT 1", (exit_plan_id,)).fetchone()

    def latest_for_order(self, conn: Connection, order_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM exit_plans WHERE order_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (order_id,)).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM exit_plans ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

