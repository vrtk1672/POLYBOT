from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.events.envelope import EventEnvelope, redact_event_data


class EventStoreRepository:
    def append_event(self, conn: Connection, envelope: EventEnvelope) -> None:
        conn.execute(
            """
            INSERT INTO event_log (
                event_id, event_type, aggregate_type, aggregate_id, source_service,
                correlation_id, causation_id, cycle_id, mode, occurred_at,
                payload_json, metadata_json, schema_version
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                envelope.event_id,
                envelope.event_type,
                envelope.aggregate_type,
                envelope.aggregate_id,
                envelope.source_service,
                envelope.correlation_id,
                envelope.causation_id,
                envelope.cycle_id,
                envelope.mode,
                envelope.occurred_at,
                Jsonb(envelope.payload),
                Jsonb(envelope.metadata),
                envelope.schema_version,
            ),
        )

    def get_event(self, conn: Connection, event_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM event_log WHERE event_id = %s", (event_id,)).fetchone()

    def list_recent_events(
        self,
        conn: Connection,
        *,
        limit: int = 100,
        event_type: str | None = None,
        correlation_id: str | None = None,
        aggregate_id: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if event_type:
            filters.append("event_type = %s")
            params.append(event_type)
        if correlation_id:
            filters.append("correlation_id = %s")
            params.append(correlation_id)
        if aggregate_id:
            filters.append("aggregate_id = %s")
            params.append(aggregate_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM event_log
            {where}
            ORDER BY stored_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def list_events_for_replay(self, conn: Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if filters.get("event_id"):
            clauses.append("event_id = %s")
            params.append(filters["event_id"])
        if filters.get("event_type"):
            clauses.append("event_type = %s")
            params.append(filters["event_type"])
        if filters.get("correlation_id"):
            clauses.append("correlation_id = %s")
            params.append(filters["correlation_id"])
        if filters.get("aggregate_id"):
            clauses.append("aggregate_id = %s")
            params.append(filters["aggregate_id"])
        if filters.get("from_time"):
            clauses.append("occurred_at >= %s")
            params.append(filters["from_time"])
        if filters.get("to_time"):
            clauses.append("occurred_at <= %s")
            params.append(filters["to_time"])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return conn.execute(
            f"""
            SELECT *
            FROM event_log
            {where}
            ORDER BY occurred_at ASC, id ASC
            LIMIT 1000
            """,
            params,
        ).fetchall()

    def delivery_attempt_count(self, conn: Connection, event_id: str, consumer_name: str) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_delivery_attempts
            WHERE event_id = %s AND consumer_name = %s
            """,
            (event_id, consumer_name),
        ).fetchone()
        return int(row["count"] or 0)

    def record_delivery_attempt(
        self,
        conn: Connection,
        *,
        event_id: str,
        consumer_name: str,
        attempt_number: int,
        status: str,
        error_message: str | None = None,
        next_retry_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO event_delivery_attempts (
                event_id, consumer_name, attempt_number, status, error_message,
                finished_at, next_retry_at, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, CASE WHEN %s IN ('SUCCESS', 'FAILED', 'RETRY_SCHEDULED', 'DLQ') THEN now() ELSE NULL END, %s, %s)
            """,
            (
                event_id,
                consumer_name,
                attempt_number,
                status,
                error_message,
                status,
                next_retry_at,
                Jsonb(metadata or {}),
            ),
        )

    def mark_delivery_success(self, conn: Connection, *, event_id: str, consumer_name: str, attempt_number: int) -> None:
        self.record_delivery_attempt(
            conn,
            event_id=event_id,
            consumer_name=consumer_name,
            attempt_number=attempt_number,
            status="SUCCESS",
        )

    def mark_delivery_failure(
        self,
        conn: Connection,
        *,
        event_id: str,
        consumer_name: str,
        attempt_number: int,
        error_message: str,
        next_retry_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        status = "RETRY_SCHEDULED" if next_retry_at else "FAILED"
        self.record_delivery_attempt(
            conn,
            event_id=event_id,
            consumer_name=consumer_name,
            attempt_number=attempt_number,
            status=status,
            error_message=error_message,
            next_retry_at=next_retry_at,
            metadata=metadata,
        )

    def move_to_dlq(
        self,
        conn: Connection,
        *,
        envelope: EventEnvelope,
        consumer_name: str,
        reason: str,
        error_message: str | None,
        attempts: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO event_dlq (
                event_id, consumer_name, reason, error_message, failed_payload_json,
                attempts, status, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'OPEN', %s)
            """,
            (
                envelope.event_id,
                consumer_name,
                reason,
                error_message,
                Jsonb(redact_event_data(envelope.payload)),
                attempts,
                Jsonb(metadata or {}),
            ),
        )

    def list_dlq(self, conn: Connection, *, limit: int = 100, status: str = "OPEN") -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM event_dlq
            WHERE status = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (status, limit),
        ).fetchall()

    def update_dlq_status(self, conn: Connection, *, dlq_id: int, status: str) -> None:
        conn.execute(
            """
            UPDATE event_dlq
            SET status = %s,
                resolved_at = CASE WHEN %s IN ('RESOLVED', 'IGNORED', 'REPLAYED') THEN now() ELSE resolved_at END
            WHERE id = %s
            """,
            (status, status, dlq_id),
        )

    def get_events_per_minute(self, conn: Connection, *, window_minutes: int = 5) -> float:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_log
            WHERE stored_at >= now() - (%s::text || ' minutes')::interval
            """,
            (window_minutes,),
        ).fetchone()
        return round(float(row["count"] or 0) / max(window_minutes, 1), 4)

    def get_event_lag(self, conn: Connection) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_events,
                MAX(stored_at) AS last_event_time
            FROM event_log
            """
        ).fetchone()
        failed = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM event_delivery_attempts
            WHERE status IN ('FAILED', 'RETRY_SCHEDULED', 'DLQ')
            """
        ).fetchone()
        dlq = conn.execute(
            """
            SELECT
                COUNT(*) AS count,
                COUNT(*) FILTER (WHERE status = 'OPEN') AS open_count
            FROM event_dlq
            """
        ).fetchone()
        consumers = conn.execute(
            """
            SELECT
                COUNT(*) AS count,
                COUNT(*) FILTER (WHERE status = 'PAUSED') AS paused_count
            FROM event_consumers
            """
        ).fetchone()
        return {
            "total_events": int(row["total_events"] or 0),
            "last_event_time": row["last_event_time"],
            "failed_events": int(failed["count"] or 0),
            "dlq_count": int(dlq["count"] or 0),
            "open_dlq_count": int(dlq["open_count"] or 0),
            "consumer_count": int(consumers["count"] or 0),
            "paused_consumers": int(consumers["paused_count"] or 0),
            "events_per_minute": self.get_events_per_minute(conn),
        }

    def replay_jobs_running(self, conn: Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM event_replay_jobs WHERE status = 'RUNNING'"
        ).fetchone()
        return int(row["count"] or 0)
