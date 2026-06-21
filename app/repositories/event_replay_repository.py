from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class EventReplayRepository:
    def create_replay_job(
        self,
        conn: Connection,
        *,
        requested_by: str,
        reason: str,
        filters: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        replay_id = f"replay_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO event_replay_jobs (
                replay_id, requested_by, reason, filter_json, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, 'PENDING', %s)
            """,
            (replay_id, requested_by, reason, Jsonb(filters), Jsonb(metadata or {})),
        )
        return replay_id

    def get_replay_job(self, conn: Connection, replay_id: str) -> dict[str, Any] | None:
        return conn.execute(
            "SELECT * FROM event_replay_jobs WHERE replay_id = %s",
            (replay_id,),
        ).fetchone()

    def mark_running(self, conn: Connection, replay_id: str) -> None:
        conn.execute(
            """
            UPDATE event_replay_jobs
            SET status = 'RUNNING',
                started_at = COALESCE(started_at, now())
            WHERE replay_id = %s
            """,
            (replay_id,),
        )

    def finish_job(self, conn: Connection, *, replay_id: str, replayed_count: int, failed_count: int) -> None:
        status = "COMPLETED" if failed_count == 0 else "FAILED"
        conn.execute(
            """
            UPDATE event_replay_jobs
            SET status = %s,
                finished_at = now(),
                replayed_count = %s,
                failed_count = %s
            WHERE replay_id = %s
            """,
            (status, replayed_count, failed_count, replay_id),
        )
