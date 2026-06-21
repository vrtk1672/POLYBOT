from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.capital.contracts import CapitalAllocationDecision


class CapitalAllocationRepository:
    def insert(self, conn: Connection, decision: CapitalAllocationDecision) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO capital_allocations_v2 (
                allocation_id, strategy_run_id, strategy_route_id, market_id, market_family, side,
                engine, bucket, allocation_status, requested_size_usd, approved_size_usd,
                max_loss_usd, reserve_after_usd, engine_budget_before_usd, engine_budget_after_usd,
                attack_bank_used_usd, profit_pocket_used_usd, base_capital_used_usd,
                allocation_reason, rejection_reason, constraints_json, dry_run
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                decision.allocation_id,
                decision.strategy_run_id,
                decision.strategy_route_id,
                decision.market_id,
                decision.market_family,
                decision.side,
                decision.engine,
                decision.bucket,
                decision.allocation_status,
                decision.requested_size_usd,
                decision.approved_size_usd,
                decision.max_loss_usd,
                decision.reserve_after_usd,
                decision.engine_budget_before_usd,
                decision.engine_budget_after_usd,
                decision.attack_bank_used_usd,
                decision.profit_pocket_used_usd,
                decision.base_capital_used_usd,
                decision.allocation_reason,
                decision.rejection_reason,
                Jsonb(decision.constraints),
                decision.dry_run,
            ),
        ).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM capital_allocations_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


