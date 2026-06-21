from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.strategy.contracts import StrategyRoute


class StrategyRouteRepository:
    def insert(self, conn: Connection, run_id: str, market_family: str | None, route: StrategyRoute) -> dict[str, Any]:
        contract = route.contract.model_dump(mode="json") if route.contract else {}
        return conn.execute(
            """
            INSERT INTO strategy_routes_v2 (
                run_id, market_id, market_family, side, selected_engine, route_status,
                opportunity_score, score_band, route_confidence, entry_price_max, target_exit,
                partial_take_profit, stop_loss, max_position_size_usd, max_position_size_contracts,
                max_loss_usd, max_hold_minutes, entry_mode, exit_mode, execution_mode,
                engine_contract_json, route_reason, risk_flags_json, no_trade_reasons_json,
                cooldown_required, insufficient_data, insufficient_data_reasons_json, reproducibility_hash
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                run_id,
                route.market_id,
                market_family,
                route.side,
                route.selected_engine,
                route.route_status,
                route.opportunity_score,
                route.score_band,
                route.route_confidence,
                route.contract.entry_price_max if route.contract else None,
                route.contract.target_exit if route.contract else None,
                route.contract.partial_take_profit if route.contract else None,
                route.contract.stop_loss if route.contract else None,
                route.contract.max_position_size_usd if route.contract else 0,
                route.contract.max_position_size_contracts if route.contract else None,
                route.contract.max_loss_usd if route.contract else 0,
                route.contract.expected_hold_minutes if route.contract else 0,
                route.contract.entry_mode if route.contract else "NONE",
                route.contract.exit_mode if route.contract else "NONE",
                "CONTRACT_ONLY",
                Jsonb(contract),
                route.route_reason,
                Jsonb(route.risk_flags),
                Jsonb(route.no_trade_reasons),
                route.cooldown_required,
                route.insufficient_data,
                Jsonb(route.insufficient_data_reasons),
                route.reproducibility_hash,
            ),
        ).fetchone()

    def latest_for_market(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM strategy_routes_v2 WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM strategy_routes_v2 ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_run(self, conn: Connection, run_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM strategy_routes_v2 WHERE run_id=%s ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()

