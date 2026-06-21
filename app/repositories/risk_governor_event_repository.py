from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class RiskGovernorEventRepository:
    def insert(self, conn: Connection, **row: Any) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO risk_governor_events (
                event_id, event_type, old_status, new_status, actor, reason, details_json, correlation_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                row["event_id"],
                row["event_type"],
                row.get("old_status"),
                row.get("new_status"),
                row.get("actor", "risk_service"),
                row.get("reason", ""),
                Jsonb(row.get("details", {})),
                row.get("correlation_id"),
            ),
        ).fetchone()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM risk_governor_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()


