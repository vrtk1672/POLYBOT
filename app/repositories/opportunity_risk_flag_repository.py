from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.opportunity.contracts import OpportunityRiskFlag


class OpportunityRiskFlagRepository:
    def insert_many(self, conn: Connection, run_id: str, market_id: str, flags: list[OpportunityRiskFlag]) -> None:
        for flag in flags:
            conn.execute(
                """
                INSERT INTO opportunity_risk_flags (
                    run_id, market_id, risk_flag, severity, source_type, source_id,
                    penalty, blocks_opportunity, explanation
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (run_id, market_id, flag.risk_flag, flag.severity, flag.source_type, flag.source_id, flag.penalty, flag.blocks_opportunity, flag.explanation),
            )

    def recent(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM opportunity_risk_flags ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

    def by_run(self, conn: Connection, run_id: str) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM opportunity_risk_flags WHERE run_id=%s ORDER BY id ASC", (run_id,)).fetchall()

