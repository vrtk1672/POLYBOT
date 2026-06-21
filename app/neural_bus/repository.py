from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_bus.contracts import NeuralEvent


class NeuralEventRepository:
    def append_event(self, conn: Connection, event: NeuralEvent) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO neural_events (
                event_id, event_type, correlation_id, market_id, candidate_id, position_id,
                source_component, source_type, priority, payload_json, created_at,
                consumed_count, status, source_table, source_record_id, schema_version,
                metadata_json
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (source_table, source_record_id, event_type)
            WHERE source_table IS NOT NULL AND source_record_id IS NOT NULL
            DO NOTHING
            RETURNING *
            """,
            (
                event.event_id,
                event.event_type,
                event.correlation_id,
                event.market_id,
                event.candidate_id,
                event.position_id,
                event.source_component,
                event.source_type,
                event.priority,
                Jsonb(event.safe_payload()),
                event.created_at,
                event.consumed_count,
                event.status,
                event.source_table,
                event.source_record_id,
                event.schema_version,
                Jsonb(event.safe_metadata()),
            ),
        ).fetchone()
        if row is not None:
            return dict(row)
        existing = conn.execute(
            """
            SELECT *
            FROM neural_events
            WHERE source_table = %s AND source_record_id = %s AND event_type = %s
            """,
            (event.source_table, event.source_record_id, event.event_type),
        ).fetchone()
        assert existing is not None
        return dict(existing)

    def get_event(self, conn: Connection, event_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM neural_events WHERE event_id = %s", (event_id,)).fetchone()
        return dict(row) if row else None

    def list_events(
        self,
        conn: Connection,
        *,
        limit: int = 100,
        event_type: str | None = None,
        market_id: str | None = None,
        correlation_id: str | None = None,
        event_id: str | None = None,
        start_id: int | None = None,
        end_id: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_id:
            clauses.append("event_id = %s")
            params.append(event_id)
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if correlation_id:
            clauses.append("correlation_id = %s")
            params.append(correlation_id)
        if start_id is not None:
            clauses.append("id >= %s")
            params.append(start_id)
        if end_id is not None:
            clauses.append("id <= %s")
            params.append(end_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM neural_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def register_consumer(
        self,
        conn: Connection,
        *,
        consumer_name: str,
        event_types: list[str],
        source_component: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        consumer_id = f"neural_consumer_{uuid4().hex}"
        row = conn.execute(
            """
            INSERT INTO neural_event_consumers (
                consumer_id, consumer_name, interested_event_types, source_component,
                status, metadata_json
            )
            VALUES (%s, %s, %s, %s, 'ACTIVE', %s)
            ON CONFLICT (consumer_name) DO UPDATE
            SET interested_event_types = EXCLUDED.interested_event_types,
                source_component = EXCLUDED.source_component,
                status = CASE WHEN neural_event_consumers.status = 'DISABLED' THEN 'DISABLED' ELSE 'ACTIVE' END,
                metadata_json = neural_event_consumers.metadata_json || EXCLUDED.metadata_json,
                updated_at = now()
            RETURNING *
            """,
            (consumer_id, consumer_name, event_types, source_component, Jsonb(metadata or {})),
        ).fetchone()
        assert row is not None
        return dict(row)

    def list_consumers(self, conn: Connection) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute("SELECT * FROM neural_event_consumers ORDER BY consumer_name").fetchall()]

    def interested_consumers(self, conn: Connection, event: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM neural_event_consumers
                WHERE status = 'ACTIVE'
                  AND %s = ANY(interested_event_types)
                  AND (source_component IS NULL OR source_component = %s)
                ORDER BY consumer_name
                """,
                (event["event_type"], event["source_component"]),
            ).fetchall()
        ]

    def record_delivery(
        self,
        conn: Connection,
        *,
        event: dict[str, Any],
        consumer: dict[str, Any],
        delivery_status: str,
        replay_id: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM neural_event_delivery
            WHERE event_id = %s AND consumer_name = %s
            """,
            (event["event_id"], consumer["consumer_name"]),
        ).fetchone()["count"]
        row = conn.execute(
            """
            INSERT INTO neural_event_delivery (
                delivery_id, event_id, consumer_id, consumer_name, replay_id,
                attempt_number, delivery_status, error_message, delivered_at,
                metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s IN ('DELIVERED', 'REPLAYED') THEN now() ELSE NULL END,
                    %s)
            ON CONFLICT DO NOTHING
            RETURNING *
            """,
            (
                f"neural_delivery_{uuid4().hex}",
                event["event_id"],
                consumer["consumer_id"],
                consumer["consumer_name"],
                replay_id,
                int(existing_count or 0) + 1,
                delivery_status,
                error_message,
                delivery_status,
                Jsonb(metadata or {}),
            ),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT *
                FROM neural_event_delivery
                WHERE event_id = %s AND consumer_name = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (event["event_id"], consumer["consumer_name"]),
            ).fetchone()
        if delivery_status in {"DELIVERED", "REPLAYED"}:
            conn.execute(
                """
                UPDATE neural_event_consumers
                SET last_delivered_event_id = %s,
                    last_delivered_at = now(),
                    updated_at = now()
                WHERE consumer_id = %s
                """,
                (event["event_id"], consumer["consumer_id"]),
            )
        return dict(row) if row else {}

    def create_replay(
        self,
        conn: Connection,
        *,
        requested_by: str,
        reason: str,
        filters: dict[str, Any],
    ) -> str:
        replay_id = f"neural_replay_{uuid4().hex}"
        conn.execute(
            """
            INSERT INTO neural_event_replay (replay_id, requested_by, reason, filter_json, status)
            VALUES (%s, %s, %s, %s, 'PENDING')
            """,
            (replay_id, requested_by, reason, Jsonb(filters)),
        )
        return replay_id

    def update_replay(
        self,
        conn: Connection,
        *,
        replay_id: str,
        status: str,
        matched_count: int,
        delivered_count: int,
        failed_count: int = 0,
        started_at: bool = False,
        finished_at: bool = False,
    ) -> None:
        conn.execute(
            f"""
            UPDATE neural_event_replay
            SET status = %s,
                matched_count = %s,
                delivered_count = %s,
                failed_count = %s,
                started_at = CASE WHEN %s THEN COALESCE(started_at, now()) ELSE started_at END,
                finished_at = CASE WHEN %s THEN now() ELSE finished_at END
            WHERE replay_id = %s
            """,
            (status, matched_count, delivered_count, failed_count, started_at, finished_at, replay_id),
        )

    def dashboard_summary(self, conn: Connection, *, limit: int = 20) -> dict[str, Any]:
        counts = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 hour') AS events_last_hour,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 day') AS events_last_day,
                COUNT(*) AS total_events
            FROM neural_events
            """
        ).fetchone()
        event_types = conn.execute(
            """
            SELECT event_type, COUNT(*) AS count, MAX(created_at) AS latest_at
            FROM neural_events
            GROUP BY event_type
            ORDER BY count DESC, event_type
            """
        ).fetchall()
        consumers = conn.execute(
            """
            SELECT c.consumer_name, c.status, c.interested_event_types, c.last_delivered_at,
                   GREATEST(0, COUNT(e.id) - COUNT(d.id)) AS lag_count
            FROM neural_event_consumers c
            LEFT JOIN neural_events e
              ON e.event_type = ANY(c.interested_event_types)
             AND (c.source_component IS NULL OR c.source_component = e.source_component)
            LEFT JOIN neural_event_delivery d
              ON d.event_id = e.event_id
             AND d.consumer_name = c.consumer_name
             AND d.delivery_status IN ('DELIVERED', 'REPLAYED')
            GROUP BY c.consumer_name, c.status, c.interested_event_types, c.last_delivered_at
            ORDER BY c.consumer_name
            """
        ).fetchall()
        failed = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM neural_event_delivery
            WHERE delivery_status = 'FAILED'
            """
        ).fetchone()
        latest = conn.execute(
            """
            SELECT e.*,
                   COUNT(d.id) FILTER (WHERE d.delivery_status IN ('DELIVERED', 'REPLAYED')) AS computed_consumed_count
            FROM neural_events e
            LEFT JOIN neural_event_delivery d ON d.event_id = e.event_id
            GROUP BY e.id
            ORDER BY e.created_at DESC, e.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return {
            "events_last_hour": int(counts["events_last_hour"] or 0),
            "events_last_day": int(counts["events_last_day"] or 0),
            "total_events": int(counts["total_events"] or 0),
            "event_types": [dict(row) for row in event_types],
            "active_consumers": len([row for row in consumers if row["status"] == "ACTIVE"]),
            "consumer_lag": [dict(row) for row in consumers],
            "failed_deliveries": int(failed["count"] or 0),
            "latest_events": [dict(row) for row in latest],
        }


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None
