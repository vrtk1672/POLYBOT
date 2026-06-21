from __future__ import annotations

from datetime import datetime

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.utils.json_safety import json_safe


class RuntimeCycleRepository:
    _STAGES = {"scanner", "intelligence", "paper", "shadow", "live"}

    def start_cycle(self, conn: Connection, cycle_id: str, mode: str, metadata: dict[str, object] | None = None) -> None:
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, metadata_json)
            VALUES (%s, %s, 'RUNNING', %s)
            ON CONFLICT (cycle_id) DO NOTHING
            """,
            (cycle_id, mode, Jsonb(json_safe(metadata or {}))),
        )

    def mark_stage_started(self, conn: Connection, cycle_id: str, stage: str) -> None:
        stage = self._normalize_stage(stage)
        conn.execute(f"UPDATE runtime_cycles_v2 SET {stage}_started = true WHERE cycle_id = %s", (cycle_id,))

    def mark_stage_finished(self, conn: Connection, cycle_id: str, stage: str) -> None:
        stage = self._normalize_stage(stage)
        conn.execute(f"UPDATE runtime_cycles_v2 SET {stage}_finished = true WHERE cycle_id = %s", (cycle_id,))

    def mark_blocked_by_mode(self, conn: Connection, cycle_id: str) -> None:
        conn.execute(
            """
            UPDATE runtime_cycles_v2
            SET blocked_by_mode = true,
                status = CASE WHEN status = 'RUNNING' THEN 'BLOCKED_BY_MODE' ELSE status END
            WHERE cycle_id = %s
            """,
            (cycle_id,),
        )

    def finish_cycle(
        self,
        conn: Connection,
        cycle_id: str,
        status: str,
        error_count: int = 0,
        warning_count: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> None:
        conn.execute(
            """
            UPDATE runtime_cycles_v2
            SET status = %s,
                finished_at = now(),
                duration_ms = LEAST(2147483647, GREATEST(0, (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)))::integer,
                error_count = %s,
                warning_count = %s,
                metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s::jsonb
            WHERE cycle_id = %s
            """,
            (status, error_count, warning_count, Jsonb(json_safe(metadata or {})), cycle_id),
        )

    def get_current_cycle(self, conn: Connection) -> dict[str, object] | None:
        return conn.execute(
            """
            SELECT *
            FROM runtime_cycles_v2
            WHERE finished_at IS NULL
              AND status IN ('RUNNING', 'STARTING')
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()

    def mark_stale_abandoned(
        self,
        conn: Connection,
        *,
        older_than: datetime,
        reason: str = "TTL_EXPIRED_ACTIVE_CYCLE",
    ) -> int:
        result = conn.execute(
            """
            UPDATE runtime_cycles_v2
            SET status = 'STALE_ABANDONED',
                finished_at = now(),
                duration_ms = LEAST(2147483647, GREATEST(0, (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)))::integer,
                warning_count = COALESCE(warning_count, 0) + 1,
                metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s::jsonb
            WHERE finished_at IS NULL
              AND status IN ('RUNNING', 'STARTING')
              AND started_at < %s
            """,
            (Jsonb(json_safe({"runtime_truth_cleanup": reason, "cleanup_state": "STALE_ABANDONED"})), older_than),
        )
        return int(result.rowcount or 0)

    def mark_open_cycles_safe_stopped(
        self,
        conn: Connection,
        *,
        reason: str = "SYSTEM_OFF",
    ) -> int:
        result = conn.execute(
            """
            UPDATE runtime_cycles_v2
            SET status = 'SAFE_STOPPED',
                finished_at = now(),
                duration_ms = GREATEST(0, (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)::integer),
                warning_count = COALESCE(warning_count, 0) + 1,
                metadata_json = COALESCE(metadata_json, '{}'::jsonb) || %s::jsonb
            WHERE finished_at IS NULL
              AND status IN ('RUNNING', 'STARTING')
            """,
            (Jsonb(json_safe({"runtime_truth_cleanup": reason, "cleanup_state": "SAFE_STOPPED"})),),
        )
        return int(result.rowcount or 0)

    def get_recent_cycles(self, conn: Connection, limit: int = 20) -> list[dict[str, object]]:
        return conn.execute(
            """
            SELECT *
            FROM runtime_cycles_v2
            ORDER BY started_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def _normalize_stage(self, stage: str) -> str:
        normalized = stage.strip().lower()
        if normalized not in self._STAGES:
            raise ValueError(f"unsupported runtime cycle stage: {stage}")
        return normalized
