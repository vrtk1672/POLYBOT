from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import FeeSnapshot


class FeeSnapshotRepository:
    def append_snapshot(self, conn: Connection, snapshot: FeeSnapshot) -> None:
        conn.execute(
            """
            INSERT INTO fee_snapshots (
                fee_snapshot_id, market_id, maker_fee, taker_fee, spread_cost,
                estimated_slippage_cost, reward_pool, reward_rate, net_edge_adjustment,
                raw_fee_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot.fee_snapshot_id,
                snapshot.market_id,
                snapshot.maker_fee,
                snapshot.taker_fee,
                snapshot.spread_cost,
                snapshot.estimated_slippage_cost,
                snapshot.reward_pool,
                snapshot.reward_rate,
                snapshot.net_edge_adjustment,
                Jsonb(snapshot.raw_fee_json),
                Jsonb(snapshot.metadata_json),
            ),
        )

    def get_latest_snapshot(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM fee_snapshots
            WHERE market_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
