from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.capital.contracts import EngineBudget


class EngineBudgetRepository:
    def upsert_many(self, conn: Connection, budgets: list[EngineBudget]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for budget in budgets:
            rows.append(
                conn.execute(
                    """
                    INSERT INTO engine_budgets (
                        engine, bucket, budget_usd, used_usd, reserved_usd, available_usd,
                        max_position_usd, max_loss_usd, max_open_allocations, cooldown_active,
                        loss_streak_multiplier, enabled, policy_json
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (engine, bucket) DO UPDATE SET
                        budget_usd=EXCLUDED.budget_usd,
                        available_usd=EXCLUDED.available_usd,
                        max_position_usd=EXCLUDED.max_position_usd,
                        max_loss_usd=EXCLUDED.max_loss_usd,
                        max_open_allocations=EXCLUDED.max_open_allocations,
                        cooldown_active=EXCLUDED.cooldown_active,
                        loss_streak_multiplier=EXCLUDED.loss_streak_multiplier,
                        enabled=EXCLUDED.enabled,
                        policy_json=EXCLUDED.policy_json,
                        updated_at=now()
                    RETURNING *
                    """,
                    (
                        budget.engine,
                        budget.bucket,
                        budget.budget_usd,
                        budget.used_usd,
                        budget.reserved_usd,
                        budget.available_usd,
                        budget.max_position_usd,
                        budget.max_loss_usd,
                        budget.max_open_allocations,
                        budget.cooldown_active,
                        budget.loss_streak_multiplier,
                        budget.enabled,
                        Jsonb(budget.policy),
                    ),
                ).fetchone()
            )
        return rows

    def list(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_budgets ORDER BY engine, bucket").fetchall()


