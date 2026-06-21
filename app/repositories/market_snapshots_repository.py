from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.market_snapshot import MarketSnapshotContract


class MarketSnapshotsRepository:
    def upsert_many(
        self,
        conn: Connection,
        snapshots: list[MarketSnapshotContract],
    ) -> dict[str, int]:
        ids: dict[str, int] = {}
        for snapshot in snapshots:
            row = conn.execute(
                """
                INSERT INTO market_snapshots (
                    cycle_id, market_id, event_id, question, slug, captured_at,
                    yes_price, no_price, last_trade_price, best_bid, best_ask, spread,
                    tick_size, liquidity, volume, volume_24h, open_interest, comment_count,
                    competitive, neg_risk, orderbook_enabled, accepting_orders,
                    time_to_close_seconds, raw_payload
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (cycle_id, market_id) DO UPDATE
                SET event_id = EXCLUDED.event_id,
                    question = EXCLUDED.question,
                    slug = EXCLUDED.slug,
                    captured_at = EXCLUDED.captured_at,
                    yes_price = EXCLUDED.yes_price,
                    no_price = EXCLUDED.no_price,
                    last_trade_price = EXCLUDED.last_trade_price,
                    best_bid = EXCLUDED.best_bid,
                    best_ask = EXCLUDED.best_ask,
                    spread = EXCLUDED.spread,
                    tick_size = EXCLUDED.tick_size,
                    liquidity = EXCLUDED.liquidity,
                    volume = EXCLUDED.volume,
                    volume_24h = EXCLUDED.volume_24h,
                    open_interest = EXCLUDED.open_interest,
                    comment_count = EXCLUDED.comment_count,
                    competitive = EXCLUDED.competitive,
                    neg_risk = EXCLUDED.neg_risk,
                    orderbook_enabled = EXCLUDED.orderbook_enabled,
                    accepting_orders = EXCLUDED.accepting_orders,
                    time_to_close_seconds = EXCLUDED.time_to_close_seconds,
                    raw_payload = EXCLUDED.raw_payload
                RETURNING id, market_id
                """,
                (
                    snapshot.cycle_id,
                    snapshot.market_id,
                    snapshot.event_id,
                    snapshot.question,
                    snapshot.slug,
                    snapshot.captured_at,
                    snapshot.yes_price,
                    snapshot.no_price,
                    snapshot.last_trade_price,
                    snapshot.best_bid,
                    snapshot.best_ask,
                    snapshot.spread,
                    snapshot.tick_size,
                    snapshot.liquidity,
                    snapshot.volume,
                    snapshot.volume_24h,
                    snapshot.open_interest,
                    snapshot.comment_count,
                    snapshot.competitive,
                    snapshot.neg_risk,
                    snapshot.orderbook_enabled,
                    snapshot.accepting_orders,
                    snapshot.time_to_close_seconds,
                    Jsonb(snapshot.raw_payload),
                ),
            ).fetchone()
            ids[str(row["market_id"])] = int(row["id"])
        return ids

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM market_snapshots
            WHERE cycle_id = %s
            ORDER BY question ASC
            """,
            (cycle_id,),
        ).fetchall()

    def get_for_cycle_market(
        self,
        conn: Connection,
        *,
        cycle_id: str,
        market_id: str,
    ) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM market_snapshots
            WHERE cycle_id = %s
              AND market_id = %s
            LIMIT 1
            """,
            (cycle_id, market_id),
        ).fetchone()

    def list_latest_catalog(self, conn: Connection) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT DISTINCT ON (market_id)
                market_id,
                question,
                slug,
                event_id,
                captured_at
            FROM market_snapshots
            ORDER BY market_id, captured_at DESC, id DESC
            """
        ).fetchall()

    def get_latest_for_market(self, conn: Connection, market_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM market_snapshots
            WHERE market_id = %s
            ORDER BY captured_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
