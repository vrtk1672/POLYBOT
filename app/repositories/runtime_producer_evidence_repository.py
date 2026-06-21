from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.runtime_producer_evidence import RuntimeProducerEvidenceItem, RuntimeProducerEvidenceRun


class RuntimeProducerEvidenceRepository:
    def list_source_status_candidates(
        self,
        conn: Connection,
        *,
        limit: int,
        producer_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not _table_exists(conn, "source_status"):
            return []
        filters: list[str] = []
        params: list[Any] = []
        if producer_names:
            normalized = {name.strip() for name in producer_names if name.strip()}
            source_names = [name for name in normalized if not name.endswith("_adapter")]
            if source_names:
                filters.append("source_name = ANY(%s)")
                params.append(source_names)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM source_status
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def record_run(self, conn: Connection, run: RuntimeProducerEvidenceRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_producer_evidence_runs (
                run_id, status, producers_checked, runtime_producers_active_before,
                runtime_producers_active_after, dry_run_only_producers_before,
                dry_run_only_producers_after, signals_created, signals_updated,
                quality_updated, processing_updated, lineage_updated, link_coverage_updated,
                provenance_updated, producer_health_updated, mesh_blockers_updated,
                paper_ready_before, paper_ready_after, orders_created, order_intents_created,
                live_actions_created, blocked_by, remaining_blockers, error_summary,
                started_at, finished_at
            )
            VALUES (
                %(run_id)s, %(status)s, %(producers_checked)s, %(runtime_producers_active_before)s,
                %(runtime_producers_active_after)s, %(dry_run_only_producers_before)s,
                %(dry_run_only_producers_after)s, %(signals_created)s, %(signals_updated)s,
                %(quality_updated)s, %(processing_updated)s, %(lineage_updated)s, %(link_coverage_updated)s,
                %(provenance_updated)s, %(producer_health_updated)s, %(mesh_blockers_updated)s,
                %(paper_ready_before)s, %(paper_ready_after)s, %(orders_created)s, %(order_intents_created)s,
                %(live_actions_created)s, %(blocked_by)s, %(remaining_blockers)s, %(error_summary)s,
                %(started_at)s, %(finished_at)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                producers_checked = EXCLUDED.producers_checked,
                runtime_producers_active_before = EXCLUDED.runtime_producers_active_before,
                runtime_producers_active_after = EXCLUDED.runtime_producers_active_after,
                dry_run_only_producers_before = EXCLUDED.dry_run_only_producers_before,
                dry_run_only_producers_after = EXCLUDED.dry_run_only_producers_after,
                signals_created = EXCLUDED.signals_created,
                signals_updated = EXCLUDED.signals_updated,
                quality_updated = EXCLUDED.quality_updated,
                processing_updated = EXCLUDED.processing_updated,
                lineage_updated = EXCLUDED.lineage_updated,
                link_coverage_updated = EXCLUDED.link_coverage_updated,
                provenance_updated = EXCLUDED.provenance_updated,
                producer_health_updated = EXCLUDED.producer_health_updated,
                mesh_blockers_updated = EXCLUDED.mesh_blockers_updated,
                paper_ready_before = FALSE,
                paper_ready_after = FALSE,
                orders_created = 0,
                order_intents_created = 0,
                live_actions_created = 0,
                blocked_by = EXCLUDED.blocked_by,
                remaining_blockers = EXCLUDED.remaining_blockers,
                error_summary = EXCLUDED.error_summary,
                finished_at = EXCLUDED.finished_at
            RETURNING *
            """,
            _run_params(run),
        ).fetchone()
        return dict(row)

    def record_item(self, conn: Connection, *, run_id: str, item: RuntimeProducerEvidenceItem) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_producer_evidence_items (
                run_id, signal_id, producer_name, source, correlation_id,
                raw_payload_ref, generated_from, generated_by, is_runtime_generated,
                is_dry_run_generated, status, evidence
            )
            VALUES (
                %(run_id)s, %(signal_id)s, %(producer_name)s, %(source)s, %(correlation_id)s,
                %(raw_payload_ref)s, %(generated_from)s, %(generated_by)s, %(is_runtime_generated)s,
                %(is_dry_run_generated)s, %(status)s, %(evidence)s
            )
            RETURNING *
            """,
            {
                "run_id": run_id,
                "signal_id": item.signal_id,
                "producer_name": item.producer_name,
                "source": item.source,
                "correlation_id": item.correlation_id,
                "raw_payload_ref": item.raw_payload_ref,
                "generated_from": item.generated_from,
                "generated_by": item.generated_by,
                "is_runtime_generated": item.is_runtime_generated,
                "is_dry_run_generated": item.is_dry_run_generated,
                "status": item.status,
                "evidence": Jsonb(json.loads(json.dumps(item.evidence, default=str))),
            },
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "runtime_producer_evidence_runs"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM runtime_producer_evidence_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def list_run_items(self, conn: Connection, run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not _table_exists(conn, "runtime_producer_evidence_items"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM runtime_producer_evidence_items
                WHERE run_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (run_id, limit),
            ).fetchall()
        ]


def _run_params(run: RuntimeProducerEvidenceRun) -> dict[str, Any]:
    data = run.model_dump()
    data["blocked_by"] = Jsonb(data.get("blocked_by") or [])
    data["remaining_blockers"] = Jsonb(data.get("remaining_blockers") or [])
    return data


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
