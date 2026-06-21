from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.risk.contracts import RiskGovernorState


class RiskGovernorStateRepository:
    def insert(self, conn: Connection, state: RiskGovernorState) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO risk_governor_state (
                state_id, runtime_mode, governor_status, kill_switch_active, attack_mode_allowed,
                cooldown_active, daily_pnl_usd, weekly_pnl_usd, daily_loss_usd, weekly_loss_usd,
                open_positions_count, open_exposure_usd, max_daily_loss_usd, max_weekly_loss_usd,
                max_open_positions, max_total_exposure_usd, max_engine_loss_json,
                max_market_family_exposure_json, active_cooldowns_json, active_breaches_json,
                manual_overrides_json, data_confidence, insufficient_data, insufficient_data_reasons_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                state.state_id,
                state.runtime_mode,
                state.governor_status,
                state.kill_switch_active,
                state.attack_mode_allowed,
                state.cooldown_active,
                state.daily_pnl_usd,
                state.weekly_pnl_usd,
                state.daily_loss_usd,
                state.weekly_loss_usd,
                state.open_positions_count,
                state.open_exposure_usd,
                state.max_daily_loss_usd,
                state.max_weekly_loss_usd,
                state.max_open_positions,
                state.max_total_exposure_usd,
                Jsonb(state.max_engine_loss),
                Jsonb(state.max_market_family_exposure),
                Jsonb(state.active_cooldowns),
                Jsonb(state.active_breaches),
                Jsonb(state.manual_overrides),
                state.data_confidence,
                state.insufficient_data,
                Jsonb(state.insufficient_data_reasons),
            ),
        ).fetchone()

    def latest(self, conn: Connection) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM risk_governor_state ORDER BY updated_at DESC, id DESC LIMIT 1").fetchone()


