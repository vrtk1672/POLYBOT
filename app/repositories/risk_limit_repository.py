from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.risk.contracts import RiskLimit


class RiskLimitRepository:
    def seed_defaults(self, conn: Connection, limits: list[RiskLimit]) -> list[dict[str, Any]]:
        rows = []
        for limit in limits:
            value = limit.value
            rows.append(conn.execute(
                """
                INSERT INTO risk_limits (
                    limit_id, scope, scope_key, limit_type, limit_value_usd, limit_value_pct,
                    limit_value_count, enabled, hard_limit, policy_json
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (limit_id) DO UPDATE SET enabled=EXCLUDED.enabled, hard_limit=EXCLUDED.hard_limit, policy_json=EXCLUDED.policy_json, updated_at=now()
                RETURNING *
                """,
                (
                    f"risk_limit_{limit.limit_type.lower()}",
                    limit.scope,
                    limit.scope_key,
                    limit.limit_type,
                    float(value) if isinstance(value, float) else None,
                    None,
                    int(value) if isinstance(value, int) and not isinstance(value, bool) else None,
                    limit.enabled,
                    limit.hard_limit,
                    Jsonb(limit.policy),
                ),
            ).fetchone())
        return rows

    def list(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM risk_limits ORDER BY scope, limit_type").fetchall()


