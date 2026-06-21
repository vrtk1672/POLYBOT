from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.strategy.contracts import EngineDecision


class EngineDecisionRepository:
    def insert_many(self, conn: Connection, run_id: str, market_id: str, decisions: list[EngineDecision]) -> None:
        for decision in decisions:
            contract = decision.contract.model_dump(mode="json") if decision.contract else {}
            conn.execute(
                """
                INSERT INTO engine_decisions (
                    run_id, market_id, engine, eligible, selected, engine_score, confidence,
                    entry_conditions_json, exit_conditions_json, risk_limits_json,
                    position_sizing_json, allowed_market_families_json, forbidden_conditions_json,
                    cooldown_triggers_json, expected_hold_minutes, entry_mode, exit_mode, rejection_reason
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    run_id,
                    market_id,
                    decision.engine,
                    decision.eligible,
                    decision.selected,
                    decision.engine_score,
                    decision.confidence,
                    Jsonb(contract.get("entry_conditions") or {}),
                    Jsonb(contract.get("exit_conditions") or {}),
                    Jsonb(contract.get("risk_limits") or {}),
                    Jsonb(contract.get("position_sizing_rules") or {}),
                    Jsonb(contract.get("allowed_market_families") or []),
                    Jsonb(contract.get("forbidden_conditions") or []),
                    Jsonb(contract.get("cooldown_triggers") or []),
                    contract.get("expected_hold_minutes") or 0,
                    contract.get("entry_mode") or "NONE",
                    contract.get("exit_mode") or "NONE",
                    decision.rejection_reason,
                ),
            )

    def by_run(self, conn: Connection, run_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_decisions WHERE run_id=%s ORDER BY id ASC", (run_id,)).fetchall()

    def summary(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT engine, COUNT(*) AS decisions, COUNT(*) FILTER (WHERE eligible) AS eligible_count,
                   COUNT(*) FILTER (WHERE selected) AS selected_count, AVG(engine_score) AS average_engine_score,
                   AVG(confidence) AS average_confidence
            FROM engine_decisions
            GROUP BY engine
            ORDER BY selected_count DESC, engine ASC
            """
        ).fetchall()

