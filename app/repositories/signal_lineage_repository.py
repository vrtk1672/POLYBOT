from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.lineage import SignalLineage


class SignalLineageRepository:
    def attach_signal_binding(self, conn: Connection, lineage: SignalLineage) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO neuron_signal_bindings (
                signal_id, neuron_name, producer_name, producer_component, producer_version,
                source_name, source_status_id, event_log_id, source_event_id, market_id,
                correlation_id, raw_payload_ref, generated_from, lineage_json
            )
            VALUES (
                %(signal_id)s, %(neuron_name)s, %(producer_name)s, %(producer_component)s,
                %(producer_version)s, %(source_name)s, %(source_status_id)s, %(event_log_id)s,
                %(source_event_id)s, %(market_id)s, %(correlation_id)s, %(raw_payload_ref)s,
                %(generated_from)s, %(lineage_json)s
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                neuron_name = EXCLUDED.neuron_name,
                producer_name = EXCLUDED.producer_name,
                producer_component = EXCLUDED.producer_component,
                producer_version = EXCLUDED.producer_version,
                source_name = EXCLUDED.source_name,
                source_status_id = EXCLUDED.source_status_id,
                event_log_id = EXCLUDED.event_log_id,
                source_event_id = EXCLUDED.source_event_id,
                market_id = EXCLUDED.market_id,
                correlation_id = EXCLUDED.correlation_id,
                raw_payload_ref = EXCLUDED.raw_payload_ref,
                generated_from = EXCLUDED.generated_from,
                lineage_json = EXCLUDED.lineage_json
            RETURNING *
            """,
            _lineage_params(lineage),
        ).fetchone()
        return dict(row)

    def get_signal_lineage(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.*,
                b.id AS binding_id,
                b.producer_name,
                b.producer_component,
                b.producer_version,
                b.source_name AS binding_source_name,
                b.source_status_id,
                b.event_log_id,
                b.source_event_id,
                b.market_id AS binding_market_id,
                b.correlation_id AS binding_correlation_id,
                b.raw_payload_ref AS binding_raw_payload_ref,
                b.generated_from,
                b.lineage_json,
                b.created_at AS binding_created_at
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            WHERE s.signal_id = %s
            """,
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_signals_by_correlation_id(self, conn: Connection, correlation_id: str, *, limit: int) -> list[dict[str, Any]]:
        return self._list_bound(conn, "COALESCE(b.correlation_id, s.correlation_id) = %s", (correlation_id,), limit)

    def list_signals_by_source(self, conn: Connection, source_name: str, *, limit: int) -> list[dict[str, Any]]:
        return self._list_bound(conn, "COALESCE(b.source_name, s.source_name) = %s", (source_name,), limit)

    def list_signals_by_producer(self, conn: Connection, producer_name: str, *, limit: int) -> list[dict[str, Any]]:
        return self._list_bound(conn, "b.producer_name = %s", (producer_name,), limit)

    def list_unbound_signals(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._list_bound(conn, "b.signal_id IS NULL", (), limit)

    def get_lineage_summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        counts = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '24 hours') AS total_signals_24h,
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '24 hours' AND b.signal_id IS NOT NULL) AS bound_signals_24h,
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '24 hours' AND b.signal_id IS NULL) AS unbound_signals_24h,
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '24 hours' AND COALESCE(b.correlation_id, s.correlation_id) IS NULL) AS signals_without_correlation_id,
                COUNT(*) FILTER (WHERE s.created_at >= now() - interval '24 hours' AND COALESCE(b.raw_payload_ref, s.raw_payload_ref) IS NULL) AS signals_without_raw_payload_ref
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            """
        ).fetchone()
        by_producer = conn.execute(
            """
            SELECT COALESCE(b.producer_name, 'unbound') AS producer_name, COUNT(*) AS count, MAX(s.created_at) AS latest_at
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            WHERE s.created_at >= now() - interval '24 hours'
            GROUP BY COALESCE(b.producer_name, 'unbound')
            ORDER BY count DESC, producer_name ASC
            """
        ).fetchall()
        by_source = conn.execute(
            """
            SELECT COALESCE(b.source_name, s.source_name, 'unknown') AS source_name, COUNT(*) AS count, MAX(s.created_at) AS latest_at
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            WHERE s.created_at >= now() - interval '24 hours'
            GROUP BY COALESCE(b.source_name, s.source_name, 'unknown')
            ORDER BY count DESC, source_name ASC
            """
        ).fetchall()
        latest_unbound = self.list_unbound_signals(conn, limit=limit)
        total = int(counts["total_signals_24h"] or 0)
        bound = int(counts["bound_signals_24h"] or 0)
        return {
            "total_signals_24h": total,
            "bound_signals_24h": bound,
            "unbound_signals_24h": int(counts["unbound_signals_24h"] or 0),
            "bound_pct_24h": round((bound / total) * 100, 2) if total else 0.0,
            "signals_by_producer": [dict(row) for row in by_producer],
            "signals_by_source": [dict(row) for row in by_source],
            "signals_without_correlation_id": int(counts["signals_without_correlation_id"] or 0),
            "signals_without_raw_payload_ref": int(counts["signals_without_raw_payload_ref"] or 0),
            "latest_unbound_signals": [dict(row) for row in latest_unbound],
        }

    def source_status_id(self, conn: Connection, source_name: str | None) -> int | None:
        if not source_name:
            return None
        row = conn.execute("SELECT id FROM source_status WHERE source_name = %s", (source_name,)).fetchone()
        return int(row["id"]) if row else None

    def _list_bound(self, conn: Connection, where: str, params: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    s.*,
                    b.id AS binding_id,
                    b.producer_name,
                    b.producer_component,
                    b.producer_version,
                    b.source_name AS binding_source_name,
                    b.source_status_id,
                    b.event_log_id,
                    b.source_event_id,
                    b.market_id AS binding_market_id,
                    b.correlation_id AS binding_correlation_id,
                    b.raw_payload_ref AS binding_raw_payload_ref,
                    b.generated_from,
                    b.lineage_json,
                    b.created_at AS binding_created_at
                FROM neuron_signals s
                LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
                WHERE {where}
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT %s
                """,
                (*params, limit),
            ).fetchall()
        ]


def _lineage_params(lineage: SignalLineage) -> dict[str, Any]:
    data = lineage.model_dump()
    data["lineage_json"] = Jsonb(json.loads(json.dumps(data.pop("lineage", {}) or {}, default=str)))
    return data
