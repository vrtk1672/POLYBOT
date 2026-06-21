from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.whale_neuron.contracts import WhaleEvent


class WhaleEventRepository:
    def ensure_scan_run(self, conn: Connection, source_id: str) -> str:
        run_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO whale_scan_runs (id, source_type, source_ref, status, scanner_version, started_at, ended_at, input_count, success_count, failure_count)
            VALUES (%s, %s, %s, 'COMPLETED', 'v2.7', %s, %s, 1, 1, 0)
            """,
            (run_id, source_id, "v2.7_manual", datetime.now(UTC), datetime.now(UTC)),
        )
        return run_id

    def insert_event(self, conn: Connection, event: WhaleEvent, *, scan_run_id: str | None = None) -> tuple[dict[str, Any], bool]:
        existing = conn.execute(
            "SELECT * FROM whale_events WHERE whale_event_id = %s OR transaction_ref = %s LIMIT 1",
            (event.whale_event_id, event.tx_hash or event.order_id or event.whale_event_id),
        ).fetchone()
        if existing:
            return existing, False
        run_id = scan_run_id or self.ensure_scan_run(conn, event.source_id)
        row_id = str(uuid4())
        row = conn.execute(
            """
            INSERT INTO whale_events (
                id, whale_scan_run_id, wallet_address, market_id, event_timestamp,
                event_direction_class, side_or_outcome, size, notional, price,
                transaction_ref, source_type, source_payload_json, detection_reason_code, detection_reason_text,
                whale_event_id, source_id, whale_id, trader_label, asset_id, side, action_type, size_usd,
                size_shares, tx_hash, order_id, event_time, raw_event_json, normalized_event_json,
                event_classification, confidence, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                row_id,
                run_id,
                event.wallet_address or event.whale_id or "unknown",
                event.market_id or "__none__",
                event.event_time,
                "UNKNOWN",
                event.side.value,
                event.size_shares or event.size_usd or 0,
                event.notional,
                event.price,
                event.tx_hash or event.order_id or event.whale_event_id,
                event.source_id,
                Jsonb(event.raw_event),
                "V2_7_WHALE_EVENT",
                "v2.7 whale event",
                event.whale_event_id,
                event.source_id,
                event.whale_id,
                event.trader_label,
                event.asset_id,
                event.side.value,
                event.action_type.value,
                event.size_usd,
                event.size_shares,
                event.tx_hash,
                event.order_id,
                event.event_time,
                Jsonb(event.raw_event),
                Jsonb(event.normalized_event),
                event.event_classification.value,
                event.confidence,
                Jsonb({}),
            ),
        ).fetchone()
        return row, True

    def get_event(self, conn: Connection, whale_event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM whale_events WHERE whale_event_id = %s OR id::text = %s", (whale_event_id, whale_event_id)).fetchone()

    def list_recent(self, conn: Connection, *, limit: int = 100, market_id: str | None = None, whale_id: str | None = None, event_classification: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if whale_id:
            clauses.append("whale_id = %s")
            params.append(whale_id)
        if event_classification:
            clauses.append("event_classification = %s")
            params.append(event_classification)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(f"SELECT * FROM whale_events {where} ORDER BY event_time DESC, created_at DESC LIMIT %s", params).fetchall()
