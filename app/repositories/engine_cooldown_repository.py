from __future__ import annotations

from typing import Any

from psycopg import Connection


class EngineCooldownRepository:
    def insert(self, conn: Connection, *, engine: str, market_id: str | None, market_family: str | None = None, cooldown_type: str, reason: str, started_at, expires_at, active: bool, severity: str, source_run_id: str | None = None) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO engine_cooldowns (
                engine, market_id, market_family, cooldown_type, reason, started_at,
                expires_at, active, severity, source_run_id
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (engine, market_id, market_family, cooldown_type, reason, started_at, expires_at, active, severity, source_run_id),
        ).fetchone()

    def active(self, conn: Connection) -> list[dict[str, Any]]:
        return conn.execute("SELECT * FROM engine_cooldowns WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now()) ORDER BY started_at DESC, id DESC").fetchall()

