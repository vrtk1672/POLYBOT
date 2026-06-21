from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_neuron.contracts import LiquiditySignal


class LiquiditySignalRepository:
    def insert_signal(self, conn: Connection, signal: LiquiditySignal) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO liquidity_signals (
                market_id, token_id, side, expected_fill_score, expected_slippage_bps,
                expected_slippage_usd, exit_quality_score, max_safe_size_usd,
                max_safe_size_contracts, liquidity_decay_score, entry_liquidity_score,
                exit_liquidity_score, liquidity_block_reason, source, raw_liquidity_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                signal.market_id, signal.token_id, signal.side.value, signal.expected_fill_score,
                signal.expected_slippage_bps, signal.expected_slippage_usd, signal.exit_quality_score,
                signal.max_safe_size_usd, signal.max_safe_size_contracts, signal.liquidity_decay_score,
                signal.entry_liquidity_score, signal.exit_liquidity_score, signal.block_reason,
                signal.source, Jsonb(json.loads(json.dumps(signal.raw_liquidity, default=str))),
            ),
        ).fetchone()
