from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.contracts import NeuronSignal


class NeuronSignalRepository:
    def create_signal(self, conn: Connection, signal: NeuronSignal) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO neuron_signals (
                signal_id, neuron, event_type, source_name, market_id, correlation_id,
                raw_direction, strength, confidence, source_reliability, freshness_seconds,
                status, evidence_json, raw_payload_ref, entity_count, evidence_count,
                processed_by_brain, consumed_at, ttl_seconds, expires_at, stale_after_seconds,
                created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(neuron)s, %(event_type)s, %(source_name)s, %(market_id)s,
                %(correlation_id)s, %(raw_direction)s, %(strength)s, %(confidence)s,
                %(source_reliability)s, %(freshness_seconds)s, %(status)s,
                %(evidence_json)s, %(raw_payload_ref)s, %(entity_count)s, %(evidence_count)s,
                %(processed_by_brain)s, %(consumed_at)s, %(ttl_seconds)s, %(expires_at)s,
                %(stale_after_seconds)s, COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _params(signal),
        ).fetchone()
        return dict(row)

    def list_recent_signals(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        neuron: str | None = None,
        market_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if neuron:
            filters.append("neuron = %s")
            params.append(neuron.strip().lower())
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        if status:
            filters.append("status = %s")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM neuron_signals
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def list_market_signals(self, conn: Connection, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_signals(conn, limit=limit, market_id=market_id)

    def list_neuron_signals(self, conn: Connection, neuron: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_signals(conn, limit=limit, neuron=neuron)

    def mark_processed(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            UPDATE neuron_signals
            SET processed_by_brain = TRUE,
                consumed_at = COALESCE(consumed_at, now()),
                updated_at = now()
            WHERE signal_id = %s
            RETURNING *
            """,
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        total_24h = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM neuron_signals
            WHERE created_at >= now() - interval '24 hours'
            """
        ).fetchone()
        per_minute = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM neuron_signals
            WHERE created_at >= now() - interval '5 minutes'
            """
        ).fetchone()
        by_neuron = conn.execute(
            """
            SELECT neuron, COUNT(*) AS count, MAX(created_at) AS latest_at
            FROM neuron_signals
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY neuron
            ORDER BY count DESC, neuron ASC
            """
        ).fetchall()
        stale = conn.execute(
            """
            SELECT *
            FROM neuron_signals
            WHERE status = 'STALE'
               OR (expires_at IS NOT NULL AND expires_at <= now())
               OR (
                    stale_after_seconds IS NOT NULL
                    AND created_at + (stale_after_seconds::text || ' seconds')::interval <= now()
               )
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest = self.list_recent_signals(conn, limit=limit)
        unprocessed = conn.execute(
            "SELECT COUNT(*) AS count FROM neuron_signals WHERE processed_by_brain = FALSE"
        ).fetchone()
        return {
            "signals_per_minute": round(float(per_minute["count"] or 0) / 5.0, 4),
            "total_signals_24h": int(total_24h["count"] or 0),
            "signals_by_neuron": [dict(row) for row in by_neuron],
            "latest_signals": [dict(row) for row in latest],
            "stale_signals": [dict(row) for row in stale],
            "unprocessed_signals": int(unprocessed["count"] or 0),
        }


def _params(signal: NeuronSignal) -> dict[str, Any]:
    data = signal.model_dump()
    data["evidence_json"] = Jsonb(json.loads(json.dumps(data.pop("evidence", {}) or {}, default=str)))
    return data
