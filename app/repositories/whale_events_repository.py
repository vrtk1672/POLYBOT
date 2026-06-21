from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.whale_event import WhaleEventContract


class WhaleEventsRepository:
    def insert(self, conn: Connection, whale_event: WhaleEventContract) -> None:
        conn.execute(
            """
            INSERT INTO whale_events (
                id, whale_scan_run_id, wallet_address, market_id, event_timestamp,
                event_direction_class, side_or_outcome, size, notional, price,
                transaction_ref, source_type, source_payload_json,
                detection_reason_code, detection_reason_text
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            """,
            (
                whale_event.id,
                whale_event.whale_scan_run_id,
                whale_event.wallet_address,
                whale_event.market_id,
                whale_event.event_timestamp,
                whale_event.event_direction_class,
                whale_event.side_or_outcome,
                whale_event.size,
                whale_event.notional,
                whale_event.price,
                whale_event.transaction_ref,
                whale_event.source_type,
                Jsonb(whale_event.source_payload_json),
                whale_event.detection_reason_code,
                whale_event.detection_reason_text,
            ),
        )

    def list_for_run(self, conn: Connection, run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_events
            WHERE whale_scan_run_id = %s
            ORDER BY event_timestamp ASC, created_at ASC
            """,
            (run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, whale_event_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM whale_events
            WHERE id = %s
            LIMIT 1
            """,
            (whale_event_id,),
        ).fetchone()

    def list_for_wallet(self, conn: Connection, wallet_address: str, limit: int) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_events
            WHERE wallet_address = %s
            ORDER BY event_timestamp DESC, created_at DESC
            LIMIT %s
            """,
            (wallet_address, limit),
        ).fetchall()

    def list_recent_markets(
        self,
        conn: Connection,
        *,
        window_start,
        window_end,
        limit: int | None = None,
    ) -> list[str]:
        query = """
            SELECT DISTINCT market_id
            FROM whale_events
            WHERE event_timestamp >= %s
              AND event_timestamp <= %s
            ORDER BY market_id ASC
        """
        params: list[object] = [window_start, window_end]
        if limit is not None:
            query += "\nLIMIT %s"
            params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        return [str(row["market_id"]) for row in rows]

    def list_for_market_in_window(
        self,
        conn: Connection,
        *,
        market_id: str,
        window_start,
        window_end,
    ) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM whale_events
            WHERE market_id = %s
              AND event_timestamp >= %s
              AND event_timestamp <= %s
            ORDER BY event_timestamp ASC, created_at ASC
            """,
            (market_id, window_start, window_end),
        ).fetchall()
