from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.risk.contracts import RiskGateDecision


class RiskGateDecisionRepository:
    def insert(self, conn: Connection, decision: RiskGateDecision) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO risk_gate_decisions (
                run_id, market_id, market_family, side, engine, decision, approved, blocked,
                risk_score, max_loss_usd, approved_max_loss_usd, approved_position_size_usd,
                liquidity_ok, slippage_ok, wording_risk_ok, correlation_ok, exposure_ok,
                engine_budget_ok, confidence_ok, exit_plan_ok, governor_ok, block_reasons_json,
                warnings_json, constraints_json, manual_override_used, override_id, explanation,
                reproducibility_hash
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                decision.run_id,
                decision.market_id,
                decision.market_family,
                decision.side,
                decision.engine,
                decision.decision,
                decision.approved,
                decision.blocked,
                decision.risk_score,
                decision.max_loss_usd,
                decision.approved_max_loss_usd,
                decision.approved_position_size_usd,
                decision.liquidity_ok,
                decision.slippage_ok,
                decision.wording_risk_ok,
                decision.correlation_ok,
                decision.exposure_ok,
                decision.engine_budget_ok,
                decision.confidence_ok,
                decision.exit_plan_ok,
                decision.governor_ok,
                Jsonb(decision.block_reasons),
                Jsonb(decision.warnings),
                Jsonb(decision.constraints),
                decision.manual_override_used,
                decision.override_id,
                decision.explanation,
                decision.reproducibility_hash,
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM risk_gate_decisions ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_run(self, conn: Connection, run_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM risk_gate_decisions WHERE run_id=%s ORDER BY id DESC LIMIT 1", (run_id,)).fetchone()


