from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import MarketSnapshotV2


class MarketSnapshotV2Repository:
    def append_snapshot(self, conn: Connection, snapshot: MarketSnapshotV2) -> None:
        conn.execute(
            """
            INSERT INTO market_snapshots_v2 (
                snapshot_id, market_id, cycle_id, correlation_id, current_price_yes, current_price_no,
                best_bid, best_ask, spread, volume_1h, volume_24h, liquidity,
                time_to_close_seconds, accepting_orders, closed, data_completeness_score,
                stale, snapshot_at, raw_snapshot_json, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, COALESCE(%s, now()), %s, %s)
            """,
            (
                snapshot.snapshot_id,
                snapshot.market_id,
                snapshot.cycle_id,
                snapshot.correlation_id,
                snapshot.current_price_yes,
                snapshot.current_price_no,
                snapshot.best_bid,
                snapshot.best_ask,
                snapshot.spread,
                snapshot.volume_1h,
                snapshot.volume_24h,
                snapshot.liquidity,
                snapshot.time_to_close_seconds,
                snapshot.accepting_orders,
                snapshot.closed,
                snapshot.data_completeness_score,
                snapshot.stale,
                snapshot.snapshot_at,
                Jsonb(snapshot.raw_snapshot_json),
                Jsonb(snapshot.metadata_json),
            ),
        )

    def get_latest_snapshot(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM market_snapshots_v2
            WHERE market_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_recent_snapshots(self, conn: Connection, market_id: str, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT * FROM market_snapshots_v2
            WHERE market_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()
