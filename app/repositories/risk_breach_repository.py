from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.risk.contracts import RiskBreach


class RiskBreachRepository:
    def insert_many(self, conn: Connection, breaches: list[RiskBreach]) -> list[dict[str, Any]]:
        rows = []
        for breach in breaches:
            rows.append(conn.execute(
                """
                INSERT INTO risk_breaches (
                    breach_id, limit_id, breach_type, severity, market_id, market_family,
                    engine, observed_value, limit_value, blocked, cooldown_created, explanation
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    breach.breach_id,
                    breach.limit_id,
                    breach.breach_type,
                    breach.severity,
                    breach.market_id,
                    breach.market_family,
                    breach.engine,
                    breach.observed_value,
                    breach.limit_value,
                    breach.blocked,
                    breach.cooldown_created,
                    breach.explanation,
                ),
            ).fetchone())
        return rows

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM risk_breaches ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


