from __future__ import annotations

import json
from typing import Any

from psycopg import Connection


class SourceStatusRepository:
    def upsert_status(self, conn: Connection, status: dict[str, Any]) -> dict[str, Any]:
        is_success = status["runtime_status"] == "ACTIVE"
        is_error = status["runtime_status"] in {"DEGRADED", "MISSING"}
        row = conn.execute(
            """
            INSERT INTO source_status (
                source_name,
                source_type,
                configured,
                key_required,
                key_present,
                key_name,
                endpoint_url,
                runtime_status,
                freshness_status,
                read_only,
                mutation_allowed,
                success_count,
                error_count,
                last_success_at,
                last_error_at,
                last_latency_ms,
                details_json,
                notes
            )
            VALUES (
                %(source_name)s,
                %(source_type)s,
                %(configured)s,
                %(key_required)s,
                %(key_present)s,
                %(key_name)s,
                %(endpoint_url)s,
                %(runtime_status)s,
                %(freshness_status)s,
                TRUE,
                FALSE,
                CASE WHEN %(is_success)s THEN 1 ELSE 0 END,
                CASE WHEN %(is_error)s THEN 1 ELSE 0 END,
                CASE WHEN %(is_success)s THEN now() ELSE NULL END,
                CASE WHEN %(is_error)s THEN now() ELSE NULL END,
                %(latency_ms)s,
                %(details_json)s::jsonb,
                %(notes)s
            )
            ON CONFLICT (source_name) DO UPDATE SET
                source_type = EXCLUDED.source_type,
                configured = EXCLUDED.configured,
                key_required = EXCLUDED.key_required,
                key_present = EXCLUDED.key_present,
                key_name = EXCLUDED.key_name,
                endpoint_url = EXCLUDED.endpoint_url,
                runtime_status = EXCLUDED.runtime_status,
                freshness_status = EXCLUDED.freshness_status,
                read_only = TRUE,
                mutation_allowed = FALSE,
                success_count = source_status.success_count + CASE WHEN %(is_success)s THEN 1 ELSE 0 END,
                error_count = source_status.error_count + CASE WHEN %(is_error)s THEN 1 ELSE 0 END,
                last_success_at = CASE WHEN %(is_success)s THEN now() ELSE source_status.last_success_at END,
                last_error_at = CASE WHEN %(is_error)s THEN now() ELSE source_status.last_error_at END,
                last_latency_ms = EXCLUDED.last_latency_ms,
                details_json = EXCLUDED.details_json,
                notes = EXCLUDED.notes,
                updated_at = now()
            RETURNING *
            """,
            {
                **status,
                "is_success": is_success,
                "is_error": is_error,
                "details_json": json.dumps(status.get("details_json") or {}),
                "latency_ms": status.get("latency_ms"),
            },
        ).fetchone()
        return dict(row)

    def list_statuses(self, conn: Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                source_name,
                source_type,
                configured,
                key_required,
                key_present,
                key_name,
                endpoint_url,
                runtime_status,
                freshness_status,
                read_only,
                mutation_allowed,
                success_count,
                error_count,
                last_success_at,
                last_error_at,
                last_latency_ms,
                details_json,
                notes,
                updated_at
            FROM source_status
            ORDER BY source_name
            """
        ).fetchall()
        return [dict(row) for row in rows]
