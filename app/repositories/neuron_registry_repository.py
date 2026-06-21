from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.registry import DEFAULT_NEURONS, NeuronHealth, NeuronRegistryEntry


class NeuronRegistryRepository:
    def ensure_default_neurons(self, conn: Connection) -> int:
        created = 0
        for item in DEFAULT_NEURONS:
            row = conn.execute(
                """
                INSERT INTO neuron_registry (
                    neuron_name, display_name, category, description, expected_signal_types,
                    producer_source, is_required_for_paper, is_required_for_live, default_status,
                    enabled, owner_component
                )
                VALUES (
                    %(neuron_name)s, %(display_name)s, %(category)s, %(description)s,
                    %(expected_signal_types)s, %(producer_source)s, %(is_required_for_paper)s,
                    %(is_required_for_live)s, %(default_status)s, %(enabled)s, %(owner_component)s
                )
                ON CONFLICT (neuron_name) DO NOTHING
                RETURNING neuron_name
                """,
                _registry_params(item),
            ).fetchone()
            if row:
                created += 1
        return created

    def list_neurons(
        self,
        conn: Connection,
        *,
        status: str | None = None,
        category: str | None = None,
        enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if status:
            filters.append("COALESCE(h.health_status, r.default_status) = %s")
            params.append(status.strip().upper())
        if category:
            filters.append("r.category = %s")
            params.append(category.strip().lower())
        if enabled is not None:
            filters.append("r.enabled = %s")
            params.append(enabled)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    r.*,
                    h.runtime_status,
                    h.health_status,
                    h.last_signal_at,
                    h.last_success_at,
                    h.last_error_at,
                    h.last_error,
                    h.stale_after_seconds,
                    h.is_stale,
                    h.expected_to_emit,
                    h.source_status_name,
                    h.signal_count_1h,
                    h.signal_count_24h,
                    h.error_count_24h,
                    h.updated_at AS health_updated_at
                FROM neuron_registry r
                LEFT JOIN neuron_health h ON h.neuron_name = r.neuron_name
                {where}
                ORDER BY r.category ASC, r.neuron_name ASC
                """,
                params,
            ).fetchall()
        ]

    def get_neuron(self, conn: Connection, neuron_name: str) -> dict[str, Any] | None:
        rows = self.list_neurons(conn)
        normalized = neuron_name.strip().lower()
        return next((row for row in rows if row["neuron_name"] == normalized), None)

    def upsert_neuron_health(self, conn: Connection, health: NeuronHealth) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO neuron_health (
                neuron_name, runtime_status, health_status, last_signal_at, last_success_at,
                last_error_at, last_error, stale_after_seconds, is_stale, expected_to_emit,
                enabled, source_status_name, signal_count_1h, signal_count_24h, error_count_24h,
                updated_at
            )
            VALUES (
                %(neuron_name)s, %(runtime_status)s, %(health_status)s, %(last_signal_at)s,
                %(last_success_at)s, %(last_error_at)s, %(last_error)s, %(stale_after_seconds)s,
                %(is_stale)s, %(expected_to_emit)s, %(enabled)s, %(source_status_name)s,
                %(signal_count_1h)s, %(signal_count_24h)s, %(error_count_24h)s, COALESCE(%(updated_at)s, now())
            )
            ON CONFLICT (neuron_name) DO UPDATE SET
                runtime_status = EXCLUDED.runtime_status,
                health_status = EXCLUDED.health_status,
                last_signal_at = EXCLUDED.last_signal_at,
                last_success_at = EXCLUDED.last_success_at,
                last_error_at = EXCLUDED.last_error_at,
                last_error = EXCLUDED.last_error,
                stale_after_seconds = EXCLUDED.stale_after_seconds,
                is_stale = EXCLUDED.is_stale,
                expected_to_emit = EXCLUDED.expected_to_emit,
                enabled = EXCLUDED.enabled,
                source_status_name = EXCLUDED.source_status_name,
                signal_count_1h = EXCLUDED.signal_count_1h,
                signal_count_24h = EXCLUDED.signal_count_24h,
                error_count_24h = EXCLUDED.error_count_24h,
                updated_at = now()
            RETURNING *
            """,
            health.model_dump(),
        ).fetchone()
        return dict(row)

    def stats_by_neuron(self, conn: Connection) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                neuron AS neuron_name,
                COUNT(*) AS total_signals,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 minute') AS signals_1m,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '5 minutes') AS signals_5m,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '1 hour') AS signals_1h,
                COUNT(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS signals_24h,
                MAX(created_at) AS last_signal_at,
                COUNT(DISTINCT market_id) FILTER (WHERE market_id IS NOT NULL) AS active_market_count,
                COUNT(*) FILTER (
                    WHERE status = 'STALE'
                       OR (expires_at IS NOT NULL AND expires_at <= now())
                       OR (
                            stale_after_seconds IS NOT NULL
                            AND created_at + (stale_after_seconds::text || ' seconds')::interval <= now()
                       )
                ) AS stale_signal_count,
                COUNT(*) FILTER (WHERE processed_by_brain = FALSE) AS unprocessed_signal_count,
                (array_agg(status ORDER BY created_at DESC, id DESC))[1] AS latest_status,
                now() AS updated_at
            FROM neuron_signals
            GROUP BY neuron
            """
        ).fetchall()
        return {str(row["neuron_name"]): dict(row) for row in rows}

    def source_status_by_name(self, conn: Connection) -> dict[str, dict[str, Any]]:
        if not _table_exists(conn, "source_status"):
            return {}
        rows = conn.execute(
            """
            SELECT source_name, runtime_status, freshness_status, last_success_at, last_error_at, error_count, notes, updated_at
            FROM source_status
            """
        ).fetchall()
        return {str(row["source_name"]): dict(row) for row in rows}


def _registry_params(item: NeuronRegistryEntry) -> dict[str, Any]:
    data = item.model_dump()
    data["expected_signal_types"] = Jsonb(json.loads(json.dumps(data["expected_signal_types"])))
    return data


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
