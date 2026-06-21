from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.market_neuron.contracts import TimeSignal


class TimeSignalRepository:
    def insert_signal(self, conn: Connection, signal: TimeSignal) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO time_signals (
                market_id, market_close_time, time_to_close_seconds, expected_hold_seconds,
                lockup_penalty_score, urgency_score, roi_per_hour_reference, time_efficiency_score,
                ttl_bucket, block_reason, source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                signal.market_id, signal.market_close_time, signal.time_to_close_seconds,
                signal.expected_hold_seconds, signal.lockup_penalty_score, signal.urgency_score,
                signal.roi_per_hour_reference, signal.time_efficiency_score, signal.ttl_bucket,
                signal.block_reason, signal.source,
            ),
        ).fetchone()

