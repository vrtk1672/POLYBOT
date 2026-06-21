from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.market_neuron.contracts import OrderbookSignal


class OrderbookSignalRepository:
    def insert_signal(self, conn: Connection, signal: OrderbookSignal) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO orderbook_signals (
                market_id, token_id, side, best_bid, best_ask, mid_price, spread, spread_bps,
                depth_1c, depth_2c, depth_5c, bid_depth_total, ask_depth_total,
                imbalance_score, queue_quality_score, cancel_burst_score, microstructure_score,
                orderbook_quality_score, has_bid_ask, stale, block_reason, source, raw_orderbook_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                signal.market_id, signal.token_id, signal.side.value, signal.best_bid, signal.best_ask,
                signal.mid_price, signal.spread, signal.spread_bps, signal.depth_1c, signal.depth_2c,
                signal.depth_5c, signal.bid_depth_total, signal.ask_depth_total, signal.imbalance_score,
                signal.queue_quality_score, signal.cancel_burst_score, signal.microstructure_score,
                signal.orderbook_quality_score, signal.has_bid_ask, signal.stale, signal.block_reason,
                signal.source, Jsonb(json.loads(json.dumps(signal.raw_orderbook, default=str))),
            ),
        ).fetchone()
