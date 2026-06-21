from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.capital.contracts import CapitalState


class CapitalStateRepository:
    def insert(self, conn: Connection, state: CapitalState) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO capital_state_v2 (
                state_id, runtime_mode, total_capital_usd, base_capital_usd, available_capital_usd,
                locked_capital_usd, open_exposure_usd, survival_reserve_usd, cash_reserve_usd,
                profit_pocket_usd, attack_bank_usd, realized_pnl_usd, unrealized_pnl_usd,
                daily_pnl_usd, weekly_pnl_usd, loss_streak_count, win_streak_count, source_type,
                source_ref, data_confidence, insufficient_data, insufficient_data_reasons_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                state.state_id,
                state.runtime_mode,
                state.total_capital_usd,
                state.base_capital_usd,
                state.available_capital_usd,
                state.locked_capital_usd,
                state.open_exposure_usd,
                state.survival_reserve_usd,
                state.cash_reserve_usd,
                state.profit_pocket_usd,
                state.attack_bank_usd,
                state.realized_pnl_usd,
                state.unrealized_pnl_usd,
                state.daily_pnl_usd,
                state.weekly_pnl_usd,
                state.loss_streak_count,
                state.win_streak_count,
                state.source_type,
                state.source_ref,
                state.data_confidence,
                state.insufficient_data,
                Jsonb(state.insufficient_data_reasons),
            ),
        ).fetchone()

    def latest(self, conn: Connection) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM capital_state_v2 ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()


