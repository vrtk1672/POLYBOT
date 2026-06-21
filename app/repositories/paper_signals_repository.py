from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.paper_signal import PaperSignalContract


class PaperSignalsRepository:
    def upsert_many(self, conn: Connection, signals: list[PaperSignalContract]) -> None:
        for signal in signals:
            conn.execute(
                """
                INSERT INTO paper_signals (
                    id, paper_run_id, cycle_id, market_id, decision_id, signal_type,
                    intended_outcome, trade_type, bucket_type, confidence, expected_edge_proxy,
                    intended_price, intended_size, guard_result, reason_code, reason_text, payload_json
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (paper_run_id, market_id) DO UPDATE
                SET decision_id = EXCLUDED.decision_id,
                    signal_type = EXCLUDED.signal_type,
                    intended_outcome = EXCLUDED.intended_outcome,
                    trade_type = EXCLUDED.trade_type,
                    bucket_type = EXCLUDED.bucket_type,
                    confidence = EXCLUDED.confidence,
                    expected_edge_proxy = EXCLUDED.expected_edge_proxy,
                    intended_price = EXCLUDED.intended_price,
                    intended_size = EXCLUDED.intended_size,
                    guard_result = EXCLUDED.guard_result,
                    reason_code = EXCLUDED.reason_code,
                    reason_text = EXCLUDED.reason_text,
                    payload_json = EXCLUDED.payload_json
                """,
                (
                    signal.id,
                    signal.paper_run_id,
                    signal.cycle_id,
                    signal.market_id,
                    signal.decision_id,
                    signal.signal_type,
                    signal.intended_outcome,
                    signal.trade_type,
                    signal.bucket_type,
                    signal.confidence,
                    signal.expected_edge_proxy,
                    signal.intended_price,
                    signal.intended_size,
                    signal.guard_result,
                    signal.reason_code,
                    signal.reason_text,
                    Jsonb(signal.payload_json),
                ),
            )

    def list_for_run(self, conn: Connection, paper_run_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM paper_signals
            WHERE paper_run_id = %s
            ORDER BY created_at ASC, market_id ASC
            """,
            (paper_run_id,),
        ).fetchall()

    def get_by_id(self, conn: Connection, paper_signal_id: str) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM paper_signals
            WHERE id = %s
            LIMIT 1
            """,
            (paper_signal_id,),
        ).fetchone()
