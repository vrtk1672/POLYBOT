from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.learning.contracts import SignalPerformance
from app.repositories.learning_repository_helpers import recent, row_dict, rows


class SignalPerformanceRepository:
    def insert(self, conn: Connection, item: SignalPerformance) -> dict[str, Any]:
        return row_dict(conn.execute(
            """
            INSERT INTO signal_performance (
                signal_perf_id, source_type, source_id, signal_type, market_id, market_family,
                direction, predicted_strength, observed_move, observed_direction,
                accuracy_score, usefulness_score, false_positive, false_negative,
                latency_seconds, confidence, evidence_json
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                item.signal_perf_id, item.source_type, item.source_id, item.signal_type,
                item.market_id, item.market_family, item.direction, item.predicted_strength,
                item.observed_move, item.observed_direction, item.accuracy_score,
                item.usefulness_score, item.false_positive, item.false_negative,
                item.latency_seconds, item.confidence, Jsonb(item.evidence),
            ),
        ).fetchone())

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return recent(conn, "signal_performance", limit)

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return rows(conn.execute(
            "SELECT source_type, signal_type, COUNT(*) AS count, AVG(accuracy_score) AS avg_accuracy, AVG(usefulness_score) AS avg_usefulness FROM signal_performance GROUP BY source_type, signal_type ORDER BY count DESC"
        ).fetchall())

