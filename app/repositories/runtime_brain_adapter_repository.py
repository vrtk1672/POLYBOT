from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.runtime_brain_adapter import RuntimeBrainInput, RuntimeBrainProducerRun


class RuntimeBrainAdapterRepository:
    def list_runtime_signal_candidates(self, conn: Connection, *, limit: int, min_quality_score: float) -> list[dict[str, Any]]:
        if not _table_exists(conn, "neuron_signals"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT
                    s.signal_id,
                    s.neuron,
                    s.event_type,
                    s.source_name,
                    s.market_id,
                    s.correlation_id,
                    s.raw_payload_ref,
                    s.status AS signal_status,
                    s.evidence_json,
                    s.created_at AS signal_created_at,
                    q.quality_score,
                    q.quality_status,
                    q.can_feed_brain,
                    q.can_feed_paper,
                    q.is_runtime_generated AS quality_is_runtime_generated,
                    q.is_dry_run_generated AS quality_is_dry_run_generated,
                    q.is_stale AS quality_is_stale,
                    ps.processing_state,
                    ps.gate_status,
                    ps.gate_blockers_json AS gate_blockers,
                    ps.can_feed_brain AS processing_can_feed_brain,
                    ps.can_feed_paper AS processing_can_feed_paper,
                    lc.lineage_status,
                    lc.lineage_trust_score,
                    lc.can_feed_brain_by_lineage,
                    lc.can_feed_paper_by_lineage,
                    link.linkability_status,
                    link.is_linked_to_market,
                    link.primary_unlinked_reason,
                    dp.generated_by,
                    dp.provenance_status,
                    dp.is_runtime_generated AS provenance_is_runtime_generated,
                    dp.is_dry_run_generated AS provenance_is_dry_run_generated,
                    b.producer_name,
                    b.generated_from,
                    EXISTS (
                        SELECT 1
                        FROM brain_output_dependencies dep
                        JOIN brain_outputs bo ON bo.brain_output_id = dep.brain_output_id
                        WHERE dep.dependency_type = 'signal'
                          AND dep.dependency_id = s.signal_id
                          AND bo.generated_by = 'runtime'
                          AND bo.brain = 'runtime_brain_adapter'
                    ) AS already_has_runtime_brain_output
                FROM neuron_signals s
                LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
                LEFT JOIN signal_processing_states ps ON ps.signal_id = s.signal_id
                LEFT JOIN signal_lineage_coverage_analysis lc ON lc.signal_id = s.signal_id
                LEFT JOIN signal_link_coverage_analysis link ON link.signal_id = s.signal_id
                LEFT JOIN dry_run_provenance_analysis dp ON dp.object_type = 'SIGNAL' AND dp.object_id = s.signal_id
                LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
                WHERE COALESCE(q.is_runtime_generated, false) = true
                  AND COALESCE(q.is_dry_run_generated, false) = false
                  AND COALESCE(dp.is_runtime_generated, false) = true
                  AND COALESCE(dp.is_dry_run_generated, false) = false
                  AND COALESCE(dp.generated_by, '') = 'runtime'
                  AND q.quality_score >= %s
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT %s
                """,
                (min_quality_score, limit),
            ).fetchall()
        ]

    def count_runtime_brain_outputs(self, conn: Connection) -> int:
        if not _table_exists(conn, "brain_outputs"):
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_outputs
            WHERE generated_by = 'runtime'
            """
        ).fetchone()
        return int(row["count"] or 0)

    def count_dry_run_brain_outputs(self, conn: Connection) -> int:
        if not _table_exists(conn, "brain_outputs"):
            return 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM brain_outputs
            WHERE generated_by IN ('mesh_dry_run', 'dry_run')
            """
        ).fetchone()
        return int(row["count"] or 0)

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

    def record_run(self, conn: Connection, run: RuntimeBrainProducerRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_brain_producer_runs (
                run_id, status, input_runtime_signals, eligible_signals,
                brain_outputs_created, brain_outputs_updated, dry_run_outputs_touched,
                runtime_brain_outputs_before, runtime_brain_outputs_after,
                dry_run_brain_outputs, coordinator_runtime_decisions,
                provenance_updated, producer_health_updated, mesh_blockers_updated,
                paper_ready_before, paper_ready_after, orders_created, order_intents_created,
                fills_created, positions_created, live_actions_created, remaining_blockers,
                started_at, finished_at, error_summary
            )
            VALUES (
                %(run_id)s, %(status)s, %(input_runtime_signals)s, %(eligible_signals)s,
                %(brain_outputs_created)s, %(brain_outputs_updated)s, %(dry_run_outputs_touched)s,
                %(runtime_brain_outputs_before)s, %(runtime_brain_outputs_after)s,
                %(dry_run_brain_outputs)s, %(coordinator_runtime_decisions)s,
                %(provenance_updated)s, %(producer_health_updated)s, %(mesh_blockers_updated)s,
                %(paper_ready_before)s, %(paper_ready_after)s, %(orders_created)s, %(order_intents_created)s,
                %(fills_created)s, %(positions_created)s, %(live_actions_created)s, %(remaining_blockers)s,
                %(started_at)s, %(finished_at)s, %(error_summary)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
                status = EXCLUDED.status,
                input_runtime_signals = EXCLUDED.input_runtime_signals,
                eligible_signals = EXCLUDED.eligible_signals,
                brain_outputs_created = EXCLUDED.brain_outputs_created,
                brain_outputs_updated = EXCLUDED.brain_outputs_updated,
                dry_run_outputs_touched = 0,
                runtime_brain_outputs_before = EXCLUDED.runtime_brain_outputs_before,
                runtime_brain_outputs_after = EXCLUDED.runtime_brain_outputs_after,
                dry_run_brain_outputs = EXCLUDED.dry_run_brain_outputs,
                coordinator_runtime_decisions = 0,
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

    def record_input(self, conn: Connection, *, run_id: str, brain_output_id: str | None, item: RuntimeBrainInput) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO runtime_brain_output_inputs (
                run_id, brain_output_id, signal_id, signal_quality_score,
                signal_processing_state, lineage_status, link_status,
                decision_type, paper_allowed, execution_allowed, evidence
            )
            VALUES (
                %(run_id)s, %(brain_output_id)s, %(signal_id)s, %(signal_quality_score)s,
                %(signal_processing_state)s, %(lineage_status)s, %(link_status)s,
                %(decision_type)s, FALSE, FALSE, %(evidence)s
            )
            RETURNING *
            """,
            {
                "run_id": run_id,
                "brain_output_id": brain_output_id,
                "signal_id": item.signal_id,
                "signal_quality_score": item.signal_quality_score,
                "signal_processing_state": item.signal_processing_state,
                "lineage_status": item.lineage_status,
                "link_status": item.link_status,
                "decision_type": item.decision_type,
                "evidence": Jsonb(json.loads(json.dumps(item.evidence, default=str))),
            },
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        if not _table_exists(conn, "runtime_brain_producer_runs"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM runtime_brain_producer_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def latest_inputs(self, conn: Connection, run_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        if not _table_exists(conn, "runtime_brain_output_inputs"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM runtime_brain_output_inputs
                WHERE run_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (run_id, limit),
            ).fetchall()
        ]


def _run_params(run: RuntimeBrainProducerRun) -> dict[str, Any]:
    data = run.model_dump()
    data["remaining_blockers"] = Jsonb(data.get("remaining_blockers") or [])
    return data


def _table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])
