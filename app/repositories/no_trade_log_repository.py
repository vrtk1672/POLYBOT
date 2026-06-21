from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.no_trade.contracts import NoTradeDecision


class NoTradeLogRepository:
    def insert(self, conn: Connection, decision: NoTradeDecision) -> dict[str, Any]:
        existing = self.find_duplicate(conn, decision)
        if existing:
            return existing
        return conn.execute(
            """
            INSERT INTO no_trade_log (
                no_trade_id, market_id, market_family, side, candidate_engine,
                source_layer, source_run_id, source_record_id, decision_status,
                primary_reason, reasons_json, risk_flags_json, opportunity_score,
                strategy_route_status, capital_allocation_status, risk_gate_decision,
                execution_block_reason, exit_block_reason, would_have_entry_price,
                would_have_size_usd, would_have_max_loss_usd, decision_confidence,
                data_confidence, insufficient_data, insufficient_data_reasons_json,
                explanation
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                decision.no_trade_id,
                decision.market_id,
                decision.market_family,
                decision.side,
                decision.candidate_engine,
                decision.source_layer,
                decision.source_run_id,
                decision.source_record_id,
                decision.decision_status,
                decision.primary_reason,
                Jsonb([reason.model_dump(mode="json") for reason in decision.reasons]),
                Jsonb(decision.risk_flags),
                decision.opportunity_score,
                decision.strategy_route_status,
                decision.capital_allocation_status,
                decision.risk_gate_decision,
                decision.execution_block_reason,
                decision.exit_block_reason,
                decision.would_have_entry_price,
                decision.would_have_size_usd,
                decision.would_have_max_loss_usd,
                decision.decision_confidence,
                decision.data_confidence,
                decision.insufficient_data,
                Jsonb(decision.insufficient_data_reasons),
                decision.explanation,
            ),
        ).fetchone()

    def find_duplicate(self, conn: Connection, decision: NoTradeDecision) -> dict[str, Any] | None:
        if not decision.source_run_id and not decision.source_record_id:
            return None
        return conn.execute(
            """
            SELECT * FROM no_trade_log
            WHERE source_layer=%s
              AND COALESCE(source_run_id,'')=COALESCE(%s,'')
              AND COALESCE(source_record_id,'')=COALESCE(%s,'')
              AND decision_status=%s
              AND primary_reason=%s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (decision.source_layer, decision.source_run_id, decision.source_record_id, decision.decision_status, decision.primary_reason),
        ).fetchone()

    def by_id(self, conn: Connection, no_trade_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM no_trade_log WHERE no_trade_id=%s LIMIT 1", (no_trade_id,)).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM no_trade_log ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

