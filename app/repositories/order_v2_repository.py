from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.execution_v2.contracts import OrderContract


class OrderV2Repository:
    def insert(self, conn: Connection, contract: OrderContract, *, order_status: str, expires_at: datetime | None = None, filled_size: float = 0.0, remaining_size: float | None = None, avg_fill_price: float | None = None) -> dict[str, Any]:
        remaining = contract.size if remaining_size is None else remaining_size
        return conn.execute(
            """
            INSERT INTO orders_v2 (
                order_id, market_id, market_family, side, token_id, engine, order_type,
                execution_mode, order_status, strategy_route_id, allocation_id, risk_gate_run_id,
                risk_decision_id, exit_plan_id, price, size, size_usd, remaining_size,
                filled_size, avg_fill_price, max_slippage_bps, ttl_seconds, expires_at,
                cancel_if_json, orderbook_snapshot_json, liquidity_snapshot_json, fee_snapshot_json,
                risk_snapshot_json, created_from, dry_run
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                contract.order_id, contract.market_id, contract.market_family, contract.side,
                contract.token_id, contract.engine, contract.order_type, contract.execution_mode,
                order_status, contract.strategy_route_id, contract.allocation_id,
                contract.risk_gate_run_id, contract.risk_decision_id, contract.exit_plan_id,
                contract.price, contract.size, contract.size_usd, remaining, filled_size,
                avg_fill_price, contract.max_slippage_bps, contract.ttl_seconds, expires_at,
                Jsonb(contract.cancel_if), Jsonb(contract.orderbook_snapshot),
                Jsonb(contract.liquidity_snapshot), Jsonb(contract.fee_snapshot),
                Jsonb(contract.risk_snapshot), contract.created_from, contract.dry_run,
            ),
        ).fetchone()

    def update_status(self, conn: Connection, order_id: str, status: str) -> dict[str, Any]:
        return conn.execute("UPDATE orders_v2 SET order_status=%s, updated_at=now() WHERE order_id=%s RETURNING *", (status, order_id)).fetchone()

    def by_order_id(self, conn: Connection, order_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM orders_v2 WHERE order_id=%s LIMIT 1", (order_id,)).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM orders_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

