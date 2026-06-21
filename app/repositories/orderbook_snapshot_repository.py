from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.data_foundation.contracts import OrderbookSnapshot
from app.events.consumers.orderbook_mesh_consumer import OrderbookMeshProofConsumer


class OrderbookSnapshotRepository:
    def append_snapshot(self, conn: Connection, snapshot: OrderbookSnapshot) -> None:
        conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, depth_1c, depth_2c, depth_5c,
                bid_depth_json, ask_depth_json, imbalance, raw_orderbook_json, metadata_json,
                depth_bid_1c, depth_ask_1c, depth_bid_2c, depth_ask_2c, depth_bid_5c, depth_ask_5c,
                total_bid_depth, total_ask_depth, liquidity_score, source, snapshot_status, is_stale,
                stale_reason, raw_payload_ref, correlation_id, collected_at, snapshot_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot.orderbook_snapshot_id,
                snapshot.market_id,
                snapshot.token_id,
                snapshot.side,
                snapshot.best_bid,
                snapshot.best_ask,
                snapshot.spread,
                snapshot.mid_price,
                snapshot.depth_1c,
                snapshot.depth_2c,
                snapshot.depth_5c,
                Jsonb(snapshot.bid_depth_json),
                Jsonb(snapshot.ask_depth_json),
                snapshot.imbalance,
                Jsonb(snapshot.raw_orderbook_json),
                Jsonb(snapshot.metadata_json),
                snapshot.depth_bid_1c,
                snapshot.depth_ask_1c,
                snapshot.depth_bid_2c,
                snapshot.depth_ask_2c,
                snapshot.depth_bid_5c,
                snapshot.depth_ask_5c,
                snapshot.total_bid_depth,
                snapshot.total_ask_depth,
                snapshot.liquidity_score,
                snapshot.source,
                snapshot.snapshot_status,
                snapshot.is_stale,
                snapshot.stale_reason,
                snapshot.raw_payload_ref,
                snapshot.correlation_id,
                snapshot.collected_at,
                snapshot.collected_at,
            ),
        )
        OrderbookMeshProofConsumer().record_snapshot_created(conn, snapshot)

    def get_latest_snapshot(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM orderbook_snapshots
            WHERE market_id = %s
            ORDER BY snapshot_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()

    def list_recent(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        market_id: str | None = None,
        source: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if source:
            clauses.append("source = %s")
            params.append(source)
        if status:
            clauses.append("snapshot_status = %s")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT * FROM orderbook_snapshots
            {where}
            ORDER BY collected_at DESC, snapshot_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
