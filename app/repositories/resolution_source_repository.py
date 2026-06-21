from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.rules_neuron.contracts import ResolutionSourceStatus


class ResolutionSourceRepository:
    def upsert_source(self, conn: Connection, source: ResolutionSourceStatus) -> dict[str, Any]:
        return conn.execute(
            """
            INSERT INTO resolution_sources (
                resolution_source_id, market_id, source_name, source_url, source_domain,
                verification_status, verification_reason, last_checked_at, reliability_score, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, now(), %s, %s)
            ON CONFLICT (resolution_source_id) DO UPDATE
            SET verification_status = EXCLUDED.verification_status,
                verification_reason = EXCLUDED.verification_reason,
                last_checked_at = now(),
                reliability_score = EXCLUDED.reliability_score,
                updated_at = now()
            RETURNING *
            """,
            (
                f"resolution_source_{uuid4().hex}",
                source.market_id,
                source.source_name,
                source.source_url,
                source.source_domain,
                source.verification_status.value if hasattr(source.verification_status, "value") else source.verification_status,
                source.verification_reason,
                source.reliability_score,
                Jsonb({}),
            ),
        ).fetchone()

    def get_latest(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        return conn.execute("SELECT * FROM resolution_sources WHERE market_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()

