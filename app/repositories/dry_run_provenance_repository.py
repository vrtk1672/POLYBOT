from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.neural_mesh.dry_run_provenance import DryRunProvenanceAnalysis


class DryRunProvenanceRepository:
    def list_recent_objects(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        objects.extend(self.list_recent_brain_outputs(conn, limit=limit))
        objects.extend(self.list_recent_coordinator_decisions(conn, limit=limit))
        objects.extend(self.list_recent_signals(conn, limit=limit))
        return objects[: limit * 3]

    def list_recent_brain_outputs(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {"object_type": "BRAIN_OUTPUT", **dict(row)}
            for row in conn.execute(
                """
                SELECT brain_output_id AS object_id, generated_by, brain AS producer_name,
                       correlation_id, metadata_json, created_at AS source_created_at
                FROM brain_outputs
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def list_recent_coordinator_decisions(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {"object_type": "COORDINATOR_DECISION", **dict(row)}
            for row in conn.execute(
                """
                SELECT
                    cd.coordinator_decision_id AS object_id,
                    cd.metadata_json,
                    cd.created_at AS source_created_at,
                    array_remove(array_agg(DISTINCT bo.generated_by), NULL) AS input_generated_by,
                    array_remove(array_agg(DISTINCT bo.brain), NULL) AS input_producers,
                    mdi.dry_run_id
                FROM coordinator_decisions cd
                LEFT JOIN coordinator_decision_inputs cdi
                    ON cdi.coordinator_decision_id = cd.coordinator_decision_id
                LEFT JOIN brain_outputs bo
                    ON bo.brain_output_id = cdi.brain_output_id
                LEFT JOIN mesh_dry_run_items mdi
                    ON mdi.coordinator_decision_id = cd.coordinator_decision_id
                GROUP BY cd.id, mdi.dry_run_id
                ORDER BY cd.created_at DESC, cd.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def list_recent_signals(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {"object_type": "SIGNAL", **dict(row)}
            for row in conn.execute(
                """
                SELECT
                    s.signal_id AS object_id,
                    s.source_name,
                    s.neuron AS producer_name,
                    s.evidence_json AS metadata_json,
                    s.created_at AS source_created_at,
                    q.is_dry_run_generated AS quality_is_dry_run_generated,
                    q.is_runtime_generated AS quality_is_runtime_generated
                FROM neuron_signals s
                LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_analysis(self, conn: Connection, analysis: DryRunProvenanceAnalysis) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO dry_run_provenance_analysis (
                object_type, object_id, generated_by, dry_run_id, producer_name,
                is_dry_run_generated, is_runtime_generated, is_adapter_generated,
                is_manual_generated, provenance_status, provenance_confidence,
                provenance_reason, can_feed_brain_by_provenance,
                can_feed_paper_by_provenance, source_table, source_created_at,
                analyzed_at, created_at, updated_at
            )
            VALUES (
                %(object_type)s, %(object_id)s, %(generated_by)s, %(dry_run_id)s,
                %(producer_name)s, %(is_dry_run_generated)s, %(is_runtime_generated)s,
                %(is_adapter_generated)s, %(is_manual_generated)s,
                %(provenance_status)s, %(provenance_confidence)s,
                %(provenance_reason)s, %(can_feed_brain_by_provenance)s,
                %(can_feed_paper_by_provenance)s, %(source_table)s,
                %(source_created_at)s, COALESCE(%(analyzed_at)s, now()), now(), now()
            )
            ON CONFLICT (object_type, object_id) DO UPDATE SET
                generated_by = EXCLUDED.generated_by,
                dry_run_id = EXCLUDED.dry_run_id,
                producer_name = EXCLUDED.producer_name,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_adapter_generated = EXCLUDED.is_adapter_generated,
                is_manual_generated = EXCLUDED.is_manual_generated,
                provenance_status = EXCLUDED.provenance_status,
                provenance_confidence = EXCLUDED.provenance_confidence,
                provenance_reason = EXCLUDED.provenance_reason,
                can_feed_brain_by_provenance = EXCLUDED.can_feed_brain_by_provenance,
                can_feed_paper_by_provenance = EXCLUDED.can_feed_paper_by_provenance,
                source_table = EXCLUDED.source_table,
                source_created_at = EXCLUDED.source_created_at,
                analyzed_at = EXCLUDED.analyzed_at,
                updated_at = now()
            RETURNING *
            """,
            analysis.model_dump(),
        ).fetchone()
        return dict(row)

    def get_analysis(self, conn: Connection, *, object_type: str, object_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM dry_run_provenance_analysis
            WHERE object_type = %s AND object_id = %s
            """,
            (object_type.strip().upper(), object_id),
        ).fetchone()
        return dict(row) if row else None

    def list_analyses(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        object_type: str | None = None,
        generated_by: str | None = None,
        provenance_status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if object_type:
            filters.append("object_type = %s")
            params.append(object_type.strip().upper())
        if generated_by:
            filters.append("generated_by = %s")
            params.append(generated_by.strip().lower())
        if provenance_status:
            filters.append("provenance_status = %s")
            params.append(provenance_status.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM dry_run_provenance_analysis
                {where}
                ORDER BY analyzed_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def record_run(self, conn: Connection, *, requested_limit: int, summary: dict[str, Any], status: str, error_summary: str | None = None) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO dry_run_provenance_runs (
                requested_limit, analyzed_count, brain_outputs_total,
                brain_outputs_runtime, brain_outputs_dry_run,
                coordinator_decisions_total, coordinator_decisions_runtime,
                coordinator_decisions_dry_run, signals_total, signals_runtime,
                signals_dry_run, unknown_count, error_count, status,
                finished_at, error_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
            RETURNING *
            """,
            (
                requested_limit,
                int(summary.get("analyzed_count") or summary.get("total_analyzed") or 0),
                int(summary.get("brain_outputs_total") or 0),
                int(summary.get("brain_outputs_runtime") or 0),
                int(summary.get("brain_outputs_dry_run") or 0),
                int(summary.get("coordinator_decisions_total") or 0),
                int(summary.get("coordinator_decisions_runtime") or 0),
                int(summary.get("coordinator_decisions_dry_run") or 0),
                int(summary.get("signals_total") or 0),
                int(summary.get("signals_runtime") or 0),
                int(summary.get("signals_dry_run") or 0),
                int(summary.get("unknown_provenance_count") or 0),
                int(summary.get("error_count") or 0),
                status,
                error_summary,
            ),
        ).fetchone()
        return dict(row)

    def summary(self, conn: Connection, *, limit: int = 20) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_analyzed,
                COUNT(*) FILTER (WHERE object_type = 'BRAIN_OUTPUT') AS brain_outputs_total,
                COUNT(*) FILTER (WHERE object_type = 'BRAIN_OUTPUT' AND is_runtime_generated) AS brain_outputs_runtime,
                COUNT(*) FILTER (WHERE object_type = 'BRAIN_OUTPUT' AND is_dry_run_generated) AS brain_outputs_dry_run,
                COUNT(*) FILTER (WHERE object_type = 'COORDINATOR_DECISION') AS coordinator_decisions_total,
                COUNT(*) FILTER (WHERE object_type = 'COORDINATOR_DECISION' AND is_runtime_generated) AS coordinator_decisions_runtime,
                COUNT(*) FILTER (WHERE object_type = 'COORDINATOR_DECISION' AND is_dry_run_generated) AS coordinator_decisions_dry_run,
                COUNT(*) FILTER (WHERE object_type = 'SIGNAL') AS signals_total,
                COUNT(*) FILTER (WHERE object_type = 'SIGNAL' AND is_runtime_generated) AS signals_runtime,
                COUNT(*) FILTER (WHERE object_type = 'SIGNAL' AND is_dry_run_generated) AS signals_dry_run,
                COUNT(*) FILTER (WHERE provenance_status = 'UNKNOWN') AS unknown_provenance_count,
                COUNT(*) FILTER (WHERE provenance_status = 'ERROR') AS error_count,
                COUNT(*) FILTER (WHERE can_feed_paper_by_provenance) AS can_feed_paper_by_provenance_count,
                COUNT(*) FILTER (WHERE NOT can_feed_paper_by_provenance) AS blocked_from_paper_count,
                MAX(analyzed_at) AS last_analysis_at
            FROM dry_run_provenance_analysis
            """
        ).fetchone()
        generated_by_counts = conn.execute(
            """
            SELECT generated_by, COUNT(*) AS count
            FROM dry_run_provenance_analysis
            GROUP BY generated_by
            ORDER BY count DESC, generated_by ASC
            """
        ).fetchall()
        status_counts = conn.execute(
            """
            SELECT provenance_status, COUNT(*) AS count
            FROM dry_run_provenance_analysis
            GROUP BY provenance_status
            ORDER BY count DESC, provenance_status ASC
            """
        ).fetchall()
        dry_run_by_id = conn.execute(
            """
            SELECT COALESCE(dry_run_id, 'unknown') AS dry_run_id, COUNT(*) AS count
            FROM dry_run_provenance_analysis
            WHERE is_dry_run_generated
            GROUP BY COALESCE(dry_run_id, 'unknown')
            ORDER BY count DESC, dry_run_id ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        producer_coverage = conn.execute(
            """
            SELECT COALESCE(producer_name, 'unknown') AS producer_name, COUNT(*) AS count
            FROM dry_run_provenance_analysis
            GROUP BY COALESCE(producer_name, 'unknown')
            ORDER BY count DESC, producer_name ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest = self.list_analyses(conn, limit=limit)
        return {
            **{key: int(totals[key] or 0) for key in totals.keys() if key != "last_analysis_at"},
            "last_analysis_at": totals["last_analysis_at"],
            "generated_by_counts": [dict(row) for row in generated_by_counts],
            "provenance_status_counts": [dict(row) for row in status_counts],
            "dry_run_by_id": [dict(row) for row in dry_run_by_id],
            "producer_name_coverage": [dict(row) for row in producer_coverage],
            "latest_analyses": latest,
        }
