from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import LiquiditySnapshot


class LiquiditySnapshotRepository:
    def append_snapshot(self, conn: Connection, snapshot: LiquiditySnapshot) -> None:
        conn.execute(
            """
            INSERT INTO liquidity_snapshots (
                liquidity_snapshot_id, market_id, orderbook_snapshot_id, liquidity_score,
                exit_quality, expected_slippage_small, expected_slippage_medium,
                expected_slippage_large, max_safe_size, fill_probability, liquidity_usd,
                depth_1c, depth_2c, depth_5c, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot.liquidity_snapshot_id,
                snapshot.market_id,
                snapshot.orderbook_snapshot_id,
                snapshot.liquidity_score,
                snapshot.exit_quality,
                snapshot.expected_slippage_small,
                snapshot.expected_slippage_medium,
                snapshot.expected_slippage_large,
                snapshot.max_safe_size,
                snapshot.fill_probability,
                snapshot.liquidity_usd,
                snapshot.depth_1c,
                snapshot.depth_2c,
                snapshot.depth_5c,
                Jsonb(snapshot.metadata_json),
            ),
        )

    def get_latest_snapshot(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM liquidity_snapshots
            WHERE market_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
