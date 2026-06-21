from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.brain_outputs import BrainOutput, BrainOutputConflict, BrainOutputDependency


class BrainOutputRepository:
    def create_brain_output(self, conn: Connection, output: BrainOutput) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO brain_outputs (
                brain_output_id, brain, output_type, market_id, position_id, recommendation,
                confidence, urgency, risk_flags_json, reasoning_summary, status, ttl_seconds,
                expires_at, correlation_id, generated_by, model_name, model_version,
                prompt_version, raw_payload_ref, metadata_json, created_at, updated_at
            )
            VALUES (
                %(brain_output_id)s, %(brain)s, %(output_type)s, %(market_id)s,
                %(position_id)s, %(recommendation)s, %(confidence)s, %(urgency)s,
                %(risk_flags_json)s, %(reasoning_summary)s, %(status)s, %(ttl_seconds)s,
                %(expires_at)s, %(correlation_id)s, %(generated_by)s, %(model_name)s,
                %(model_version)s, %(prompt_version)s, %(raw_payload_ref)s,
                %(metadata_json)s, COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _output_params(output),
        ).fetchone()
        return dict(row)

    def add_dependency(self, conn: Connection, dependency: BrainOutputDependency) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO brain_output_dependencies (
                brain_output_id, dependency_type, dependency_id, dependency_role, confidence, created_at
            )
            VALUES (
                %(brain_output_id)s, %(dependency_type)s, %(dependency_id)s,
                %(dependency_role)s, %(confidence)s, COALESCE(%(created_at)s, now())
            )
            RETURNING *
            """,
            dependency.model_dump(),
        ).fetchone()
        return dict(row)

    def add_conflict(self, conn: Connection, conflict: BrainOutputConflict) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO brain_output_conflicts (
                brain_output_id, conflicts_with_type, conflicts_with_id, conflict_type,
                conflict_reason, conflict_severity, created_at
            )
            VALUES (
                %(brain_output_id)s, %(conflicts_with_type)s, %(conflicts_with_id)s,
                %(conflict_type)s, %(conflict_reason)s, %(conflict_severity)s,
                COALESCE(%(created_at)s, now())
            )
            RETURNING *
            """,
            conflict.model_dump(),
        ).fetchone()
        return dict(row)

    def get_brain_output(self, conn: Connection, brain_output_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM brain_outputs WHERE brain_output_id = %s",
            (brain_output_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_recent_brain_outputs(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        brain: str | None = None,
        market_id: str | None = None,
        position_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if brain:
            filters.append("brain = %s")
            params.append(brain.strip().lower())
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        if position_id:
            filters.append("position_id = %s")
            params.append(position_id)
        if status:
            filters.append("status = %s")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM brain_outputs
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def list_outputs_by_market(self, conn: Connection, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_brain_outputs(conn, market_id=market_id, limit=limit)

    def list_outputs_by_brain(self, conn: Connection, brain: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_brain_outputs(conn, brain=brain, limit=limit)

    def list_outputs_by_signal_dependency(self, conn: Connection, signal_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT bo.*
            FROM brain_outputs bo
            JOIN brain_output_dependencies dep
                ON dep.brain_output_id = bo.brain_output_id
            WHERE dep.dependency_type = 'signal'
              AND dep.dependency_id = %s
            ORDER BY bo.created_at DESC, bo.id DESC
            LIMIT %s
            """,
            (signal_id, limit),
        ).fetchall()

    def list_dependencies(self, conn: Connection, brain_output_id: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT brain_output_id, dependency_type, dependency_id, dependency_role, confidence, created_at
            FROM brain_output_dependencies
            WHERE brain_output_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (brain_output_id,),
        ).fetchall()

    def list_conflicts_for_output(self, conn: Connection, brain_output_id: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT brain_output_id, conflicts_with_type, conflicts_with_id, conflict_type,
                   conflict_reason, conflict_severity, created_at
            FROM brain_output_conflicts
            WHERE brain_output_id = %s
            ORDER BY conflict_severity DESC NULLS LAST, created_at DESC, id DESC
            """,
            (brain_output_id,),
        ).fetchall()

    def list_conflicts(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT brain_output_id, conflicts_with_type, conflicts_with_id, conflict_type,
                   conflict_reason, conflict_severity, created_at
            FROM brain_output_conflicts
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def signal_exists(self, conn: Connection, signal_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM neuron_signals WHERE signal_id = %s", (signal_id,)).fetchone()
        return row is not None

    def brain_output_exists(self, conn: Connection, brain_output_id: str) -> bool:
        row = conn.execute("SELECT 1 FROM brain_outputs WHERE brain_output_id = %s", (brain_output_id,)).fetchone()
        return row is not None

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS total_outputs_24h,
                COUNT(*) FILTER (
                    WHERE status = 'ACTIVE'
                      AND (expires_at IS NULL OR expires_at > now())
                ) AS active_outputs,
                COUNT(*) FILTER (
                    WHERE status = 'EXPIRED'
                       OR (expires_at IS NOT NULL AND expires_at <= now())
                ) AS expired_outputs,
                COUNT(*) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1 FROM brain_output_dependencies dep
                        WHERE dep.brain_output_id = brain_outputs.brain_output_id
                    )
                ) AS outputs_without_dependencies
            FROM brain_outputs
            """
        ).fetchone()
        by_brain = conn.execute(
            """
            SELECT brain, COUNT(*) AS count, MAX(created_at) AS latest_at
            FROM brain_outputs
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY brain
            ORDER BY count DESC, brain ASC
            """
        ).fetchall()
        by_status = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM brain_outputs
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY status
            ORDER BY count DESC, status ASC
            """
        ).fetchall()
        latest = self.list_recent_brain_outputs(conn, limit=limit)
        conflicts = self.list_conflicts(conn, limit=limit)
        signals_with_outputs = conn.execute(
            """
            SELECT COUNT(DISTINCT dependency_id) AS count
            FROM brain_output_dependencies
            WHERE dependency_type = 'signal'
            """
        ).fetchone()
        return {
            "total_outputs_24h": int(totals["total_outputs_24h"] or 0),
            "active_outputs": int(totals["active_outputs"] or 0),
            "expired_outputs": int(totals["expired_outputs"] or 0),
            "outputs_by_brain": [dict(row) for row in by_brain],
            "outputs_by_status": [dict(row) for row in by_status],
            "latest_outputs": [dict(row) for row in latest],
            "recent_conflicts": [dict(row) for row in conflicts],
            "outputs_without_dependencies": int(totals["outputs_without_dependencies"] or 0),
            "signals_with_outputs": int(signals_with_outputs["count"] or 0),
        }


def _output_params(output: BrainOutput) -> dict[str, Any]:
    data = output.model_dump()
    data["risk_flags_json"] = Jsonb(json.loads(json.dumps(data.pop("risk_flags", []) or [], default=str)))
    data["metadata_json"] = Jsonb(json.loads(json.dumps(data.pop("metadata", {}) or {}, default=str)))
    return data
