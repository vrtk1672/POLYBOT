from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.risk.contracts import CooldownEvent


class CooldownEventRepository:
    def insert_many(self, conn: Connection, cooldowns: list[CooldownEvent]) -> list[dict[str, Any]]:
        rows = []
        for cooldown in cooldowns:
            rows.append(conn.execute(
                """
                INSERT INTO cooldown_events (
                    cooldown_id, scope, scope_key, engine, market_family, market_id,
                    reason, severity, started_at, expires_at, active, source_breach_id
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s)
                RETURNING *
                """,
                (
                    cooldown.cooldown_id,
                    cooldown.scope,
                    cooldown.scope_key,
                    cooldown.engine,
                    cooldown.market_family,
                    cooldown.market_id,
                    cooldown.reason,
                    cooldown.severity,
                    cooldown.expires_at,
                    cooldown.active,
                    cooldown.source_breach_id,
                ),
            ).fetchone())
        return rows

    def active(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM cooldown_events WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now()) ORDER BY created_at DESC").fetchall()

    def recent(self, conn: Connection, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM cooldown_events ORDER BY created_at DESC, id DESC LIMIT %s", (limit,)).fetchall()

