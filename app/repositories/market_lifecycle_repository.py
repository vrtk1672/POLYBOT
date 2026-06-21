from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb


class MarketLifecycleRepository:
    def insert_event(
        self,
        conn: Connection,
        *,
        market_id: str,
        event_type: str,
        previous_status: str | None = None,
        new_status: str | None = None,
        source_service: str = "data_foundation",
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO market_lifecycle_events (
                lifecycle_event_id, market_id, event_type, previous_status, new_status,
                source_service, correlation_id, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                f"life_{uuid4().hex}",
                market_id,
                event_type,
                previous_status,
                new_status,
                source_service,
                correlation_id,
                Jsonb(metadata or {}),
            ),
        ).fetchone()
        return row

    def latest_event(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute(
            """
            SELECT * FROM market_lifecycle_events
            WHERE market_id = %s
            ORDER BY event_at DESC, id DESC
            LIMIT 1
            """,
            (market_id,),
        ).fetchone()
