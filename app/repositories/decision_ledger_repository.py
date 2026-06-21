from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.domain.contracts.decision import DecisionLedgerContract


class DecisionLedgerRepository:
    def upsert_many(
        self,
        conn: Connection,
        decisions: list[DecisionLedgerContract],
    ) -> None:
        for decision in decisions:
            conn.execute(
                """
                INSERT INTO decision_ledger (
                    id, cycle_id, market_snapshot_id, ranking_snapshot_id, market_id, decision_type,
                    selected, reason, confidence, trade_type, bucket_type, expected_edge_proxy,
                    invalidation_rules, metadata
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                ON CONFLICT (cycle_id, market_id) DO UPDATE
                SET ranking_snapshot_id = EXCLUDED.ranking_snapshot_id,
                    decision_type = EXCLUDED.decision_type,
                    selected = EXCLUDED.selected,
                    reason = EXCLUDED.reason,
                    confidence = EXCLUDED.confidence,
                    trade_type = EXCLUDED.trade_type,
                    bucket_type = EXCLUDED.bucket_type,
                    expected_edge_proxy = EXCLUDED.expected_edge_proxy,
                    invalidation_rules = EXCLUDED.invalidation_rules,
                    metadata = EXCLUDED.metadata
                """,
                (
                    decision.id,
                    decision.cycle_id,
                    decision.market_snapshot_id,
                    decision.ranking_snapshot_id,
                    decision.market_id,
                    decision.decision_type,
                    decision.selected,
                    decision.reason,
                    decision.confidence,
                    decision.trade_type,
                    decision.bucket_type,
                    decision.expected_edge_proxy,
                    Jsonb(decision.invalidation_rules),
                    Jsonb(decision.metadata),
                ),
            )

    def list_for_cycle(self, conn: Connection, cycle_id: str) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM decision_ledger
            WHERE cycle_id = %s
            ORDER BY selected DESC, market_id ASC
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
            FROM decision_ledger
            WHERE cycle_id = %s
              AND market_id = %s
            LIMIT 1
            """,
            (cycle_id, market_id),
        ).fetchone()
