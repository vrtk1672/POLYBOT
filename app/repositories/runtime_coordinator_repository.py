from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.runtime_coordinator import RuntimeCoordinatorInput, RuntimeCoordinatorRun


class RuntimeCoordinatorRepository:
    def list_runtime_brain_output_candidates(self, conn: Connection, *, limit: int, min_brain_confidence: float) -> list[dict[str, Any]]:
        if not _table_exists(conn, "brain_outputs"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    bo.brain_output_id,
                    bo.brain,
                    bo.output_type,
                    bo.market_id,
                    bo.position_id,
                    bo.recommendation,
                    bo.confidence,
                    bo.urgency,
                    bo.risk_flags_json,
                    bo.correlation_id,
                    bo.raw_payload_ref,
                    bo.generated_by,
                    bo.metadata_json,
                    bo.created_at AS brain_output_created_at,
                    array_remove(array_agg(DISTINCT dep.dependency_id) FILTER (WHERE dep.dependency_type = 'signal'), NULL) AS source_signal_ids,
                    EXISTS (
                        SELECT 1
                        FROM coordinator_decision_inputs cdi
                        JOIN coordinator_decisions cd ON cd.coordinator_decision_id = cdi.coordinator_decision_id
                        WHERE cdi.brain_output_id = bo.brain_output_id
                          AND cd.metadata_json->>'generated_by' = 'runtime'
                          AND cd.metadata_json->>'producer_name' = 'runtime_coordinator_adapter'
                    ) AS already_has_runtime_coordinator_decision
                FROM brain_outputs bo
                LEFT JOIN brain_output_dependencies dep
                    ON dep.brain_output_id = bo.brain_output_id
                WHERE bo.generated_by = 'runtime'
                  AND bo.brain = 'runtime_brain_adapter'
                  AND COALESCE(bo.confidence, 0) >= %s
                  AND COALESCE(bo.metadata_json->>'is_runtime_generated', 'false') = 'true'
                  AND COALESCE(bo.metadata_json->>'is_dry_run_generated', 'false') = 'false'
                  AND COALESCE(bo.metadata_json->>'execution_allowed', 'false') = 'false'
                  AND COALESCE(bo.metadata_json->>'paper_allowed', 'false') = 'false'
                GROUP BY bo.id
                ORDER BY bo.created_at DESC, bo.id DESC
                LIMIT %s
                """,
                (min_brain_confidence, limit),
            ).fetchall()
        ]

    def count_runtime_coordinator_decisions(self, conn: Connection) -> int:
        if not _table_exists(conn, "dry_run_provenance_analysis"):
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM dry_run_provenance_analysis
            WHERE object_type = 'COORDINATOR_DECISION'
              AND is_runtime_generated = true
            """
        ).fetchone()
        return int(row["count"] or 0)

    def count_dry_run_coordinator_decisions(self, conn: Connection) -> int:
        if not _table_exists(conn, "dry_run_provenance_analysis"):
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM dry_run_provenance_analysis
            WHERE object_type = 'COORDINATOR_DECISION'
              AND is_dry_run_generated = true
            """
        ).fetchone()
        return int(row["count"] or 0)

    def count_runtime_brain_outputs(self, conn: Connection) -> int:
        if not _table_exists(conn, "brain_outputs"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS count FROM brain_outputs WHERE generated_by = 'runtime'").fetchone()
        return int(row["count"] or 0)

    def count_dry_run_brain_outputs(self, conn: Connection) -> int:
        if not _table_exists(conn, "brain_outputs"):
            return 0
        row = conn.execute("SELECT COUNT(*) AS count FROM brain_outputs WHERE generated_by IN ('mesh_dry_run', 'dry_run')").fetchone()
        return int(row["count"] or 0)

    def record_run(self, conn: Connection, run: RuntimeCoordinatorRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_coordinator_runs (
                run_id, status, input_runtime_brain_outputs, eligible_brain_outputs,
                coordinator_decisions_created, coordinator_decisions_updated,
                dry_run_decisions_touched, runtime_coordinator_decisions_before,
                runtime_coordinator_decisions_after, dry_run_coordinator_decisions,
                runtime_brain_outputs, dry_run_brain_outputs, provenance_updated,
                producer_health_updated, mesh_blockers_updated, paper_ready_before,
                paper_ready_after, orders_created, order_intents_created, fills_created,
                positions_created, live_actions_created, remaining_blockers,
                started_at, finished_at, error_summary
            )
            VALUES (
                %(run_id)s, %(status)s, %(input_runtime_brain_outputs)s, %(eligible_brain_outputs)s,
                %(coordinator_decisions_created)s, %(coordinator_decisions_updated)s,
                0, %(runtime_coordinator_decisions_before)s,
                %(runtime_coordinator_decisions_after)s, %(dry_run_coordinator_decisions)s,
                %(runtime_brain_outputs)s, %(dry_run_brain_outputs)s, %(provenance_updated)s,
                %(producer_health_updated)s, %(mesh_blockers_updated)s, FALSE,
                FALSE, 0, 0, 0, 0, 0, %(remaining_blockers)s,
                %(started_at)s, %(finished_at)s, %(error_summary)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                input_runtime_brain_outputs = EXCLUDED.input_runtime_brain_outputs,
                eligible_brain_outputs = EXCLUDED.eligible_brain_outputs,
                coordinator_decisions_created = EXCLUDED.coordinator_decisions_created,
                coordinator_decisions_updated = EXCLUDED.coordinator_decisions_updated,
                dry_run_decisions_touched = 0,
                runtime_coordinator_decisions_before = EXCLUDED.runtime_coordinator_decisions_before,
                runtime_coordinator_decisions_after = EXCLUDED.runtime_coordinator_decisions_after,
                dry_run_coordinator_decisions = EXCLUDED.dry_run_coordinator_decisions,
                runtime_brain_outputs = EXCLUDED.runtime_brain_outputs,
                dry_run_brain_outputs = EXCLUDED.dry_run_brain_outputs,
                provenance_updated = EXCLUDED.provenance_updated,
                producer_health_updated = EXCLUDED.producer_health_updated,
                mesh_blockers_updated = EXCLUDED.mesh_blockers_updated,
                paper_ready_before = FALSE,
                paper_ready_after = FALSE,
                orders_created = 0,
                order_intents_created = 0,
                fills_created = 0,
                positions_created = 0,
                live_actions_created = 0,
                remaining_blockers = EXCLUDED.remaining_blockers,
                finished_at = EXCLUDED.finished_at,
                error_summary = EXCLUDED.error_summary
            RETURNING *
            """,
            _run_params(run),
        ).fetchone()
        return dict(row)

    def record_input(self, conn: Connection, *, run_id: str, coordinator_decision_id: str | None, item: RuntimeCoordinatorInput) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_coordinator_decision_inputs (
                run_id, coordinator_decision_id, brain_output_id, signal_ids,
                brain_confidence, brain_decision_type, coordinator_decision_type,
                paper_allowed, execution_allowed, order_intent_allowed, evidence
            )
            VALUES (
                %(run_id)s, %(coordinator_decision_id)s, %(brain_output_id)s, %(signal_ids)s,
                %(brain_confidence)s, %(brain_decision_type)s, %(coordinator_decision_type)s,
                FALSE, FALSE, FALSE, %(evidence)s
            )
            RETURNING *
            """,
            {
                "run_id": run_id,
                "coordinator_decision_id": coordinator_decision_id,
                "brain_output_id": item.brain_output_id,
                "signal_ids": Jsonb(item.source_signal_ids),
                "brain_confidence": item.brain_confidence,
                "brain_decision_type": item.brain_decision_type,
                "coordinator_decision_type": item.coordinator_decision_type,
                "evidence": Jsonb(json.loads(json.dumps(item.evidence, default=str))),
            },
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "runtime_coordinator_runs"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM runtime_coordinator_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def latest_inputs(self, conn: Connection, run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not _table_exists(conn, "runtime_coordinator_decision_inputs"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM runtime_coordinator_decision_inputs
                WHERE run_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (run_id, limit),
            ).fetchall()
        ]


def _run_params(run: RuntimeCoordinatorRun) -> dict[str, Any]:
    data = run.model_dump()
    data["remaining_blockers"] = Jsonb(data.get("remaining_blockers") or [])
    return data


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
