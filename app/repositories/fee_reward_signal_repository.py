from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_neuron.contracts import FeeRewardSignal


class FeeRewardSignalRepository:
    def insert_signal(self, conn: Connection, signal: FeeRewardSignal) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO fee_reward_signals (
                market_id, token_id, side, maker_cost_bps, taker_cost_bps, spread_cost_bps,
                slippage_cost_bps, reward_pool_usd, reward_score, net_edge_after_costs,
                fee_penalty_score, friction_score, block_reason, source, raw_fee_reward_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                signal.market_id, signal.token_id, signal.side.value, signal.maker_cost_bps,
                signal.taker_cost_bps, signal.spread_cost_bps, signal.slippage_cost_bps,
                signal.reward_pool_usd, signal.reward_score, signal.net_edge_after_costs,
                signal.fee_penalty_score, signal.friction_score, signal.block_reason,
                signal.source, Jsonb(json.loads(json.dumps(signal.raw_fee_reward, default=str))),
            ),
        ).fetchone()
