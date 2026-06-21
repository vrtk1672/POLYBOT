from __future__ import annotations

from psycopg import Connection
from psycopg.types.json import Jsonb


SERVICE_STATUSES = {"RUNNING", "HEALTHY", "DEGRADED", "STALE", "ERROR", "STOPPED", "BLOCKED_BY_MODE"}


class ServiceHealthRepository:
    def upsert_service_health(
        self,
        conn: Connection,
        *,
        service_name: str,
        service_type: str,
        status: str,
        details: dict[str, object] | None = None,
    ) -> None:
        status = _normalize_status(status)
        conn.execute(
            """
            INSERT INTO service_health (service_name, service_type, status, details_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (service_name) DO UPDATE
            SET service_type = EXCLUDED.service_type,
                status = EXCLUDED.status,
                details_json = EXCLUDED.details_json,
                updated_at = now()
            """,
            (service_name, service_type, status, Jsonb(details or {})),
        )

    def mark_heartbeat(self, conn: Connection, service_name: str, *, status: str = "RUNNING") -> None:
        status = _normalize_status(status)
        conn.execute(
            """
            UPDATE service_health
            SET status = %s,
                last_heartbeat_at = now(),
                updated_at = now()
            WHERE service_name = %s
            """,
            (status, service_name),
        )

    def mark_success(self, conn: Connection, service_name: str, details: dict[str, object] | None = None) -> None:
        conn.execute(
            """
            UPDATE service_health
            SET status = 'HEALTHY',
                last_success_at = now(),
                details_json = COALESCE(details_json, '{}'::jsonb) || %s::jsonb,
                updated_at = now()
            WHERE service_name = %s
            """,
            (Jsonb(details or {}), service_name),
        )

    def mark_error(self, conn: Connection, service_name: str, details: dict[str, object] | None = None) -> None:
        conn.execute(
            """
            UPDATE service_health
            SET status = 'ERROR',
                last_error_at = now(),
                error_count = error_count + 1,
                details_json = COALESCE(details_json, '{}'::jsonb) || %s::jsonb,
                updated_at = now()
            WHERE service_name = %s
            """,
            (Jsonb(details or {}), service_name),
        )

    def list_services(self, conn: Connection) -> list[dict[str, object]]:
        return conn.execute("SELECT * FROM service_health ORDER BY service_name ASC").fetchall()

    def get_overall_health(self, conn: Connection) -> dict[str, object]:
        rows = self.list_services(conn)
        statuses = {str(row["status"]) for row in rows}
        if "ERROR" in statuses:
            status = "ERROR"
        elif statuses & {"DEGRADED", "STALE", "BLOCKED_BY_MODE"}:
            status = "DEGRADED"
        else:
            status = "HEALTHY"
        return {"overall_status": status, "service_count": len(rows)}


def _normalize_status(status: str) -> str:
    normalized = status.strip().upper()
    if normalized not in SERVICE_STATUSES:
        raise ValueError(f"unsupported service health status: {status}")
    return normalized
