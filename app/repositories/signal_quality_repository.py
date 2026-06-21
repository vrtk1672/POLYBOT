from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.signal_quality import SignalQualityEvaluation


class SignalQualityRepository:
    def get_signal_context(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.*,
                b.signal_id IS NOT NULL AS has_binding,
                b.producer_name,
                b.source_name AS binding_source_name,
                b.correlation_id AS binding_correlation_id,
                b.raw_payload_ref AS binding_raw_payload_ref,
                b.generated_from,
                EXISTS (
                    SELECT 1 FROM signal_market_links sml
                    WHERE sml.signal_id = s.signal_id
                ) AS linked_to_market,
                EXISTS (
                    SELECT 1 FROM signal_position_links spl
                    WHERE spl.signal_id = s.signal_id
                ) AS linked_to_position,
                EXISTS (
                    SELECT 1 FROM brain_output_dependencies dep
                    WHERE dep.dependency_type = 'signal'
                      AND dep.dependency_id = s.signal_id
                ) AS used_by_brain_output,
                EXISTS (
                    SELECT 1
                    FROM brain_output_dependencies dep
                    JOIN coordinator_decision_inputs cdi
                      ON cdi.brain_output_id = dep.brain_output_id
                    WHERE dep.dependency_type = 'signal'
                      AND dep.dependency_id = s.signal_id
                ) AS used_by_coordinator,
                EXISTS (
                    SELECT 1 FROM neuron_signal_evidence ev
                    WHERE ev.signal_id = s.signal_id
                ) AS has_evidence_rows,
                EXISTS (
                    SELECT 1 FROM signal_market_links sml
                    WHERE sml.signal_id = s.signal_id
                      AND COALESCE(sml.created_by, '') <> 'mesh_dry_run'
                ) AS has_non_dry_run_market_link
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            WHERE s.signal_id = %s
            """,
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_recent_signal_ids(self, conn: Connection, *, limit: int = 100) -> list[str]:
        return [
            str(row["signal_id"])
            for row in conn.execute(
                """
                SELECT signal_id
                FROM neuron_signals
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def list_unevaluated_signal_ids(self, conn: Connection, *, limit: int = 100) -> list[str]:
        return [
            str(row["signal_id"])
            for row in conn.execute(
                """
                SELECT s.signal_id
                FROM neuron_signals s
                LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
                WHERE q.signal_id IS NULL
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_evaluation(self, conn: Connection, evaluation: SignalQualityEvaluation) -> dict[str, Any]:
        params = _evaluation_params(evaluation)
        row = conn.execute(
            """
            INSERT INTO signal_quality_evaluations (
                signal_id, quality_score, quality_status, missing_fields_json,
                readiness_reason, can_feed_brain, can_feed_paper, has_market_id,
                has_source, has_lineage, has_correlation_id, has_raw_payload_ref,
                has_confidence, has_strength, has_freshness, has_evidence,
                linked_to_market, linked_to_position, used_by_brain_output,
                used_by_coordinator, is_dry_run_generated, is_runtime_generated,
                is_stale, evaluated_at, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(quality_score)s, %(quality_status)s,
                %(missing_fields_json)s, %(readiness_reason)s, %(can_feed_brain)s,
                %(can_feed_paper)s, %(has_market_id)s, %(has_source)s,
                %(has_lineage)s, %(has_correlation_id)s, %(has_raw_payload_ref)s,
                %(has_confidence)s, %(has_strength)s, %(has_freshness)s,
                %(has_evidence)s, %(linked_to_market)s, %(linked_to_position)s,
                %(used_by_brain_output)s, %(used_by_coordinator)s,
                %(is_dry_run_generated)s, %(is_runtime_generated)s, %(is_stale)s,
                COALESCE(%(evaluated_at)s, now()), COALESCE(%(created_at)s, now()),
                %(updated_at)s
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                quality_score = EXCLUDED.quality_score,
                quality_status = EXCLUDED.quality_status,
                missing_fields_json = EXCLUDED.missing_fields_json,
                readiness_reason = EXCLUDED.readiness_reason,
                can_feed_brain = EXCLUDED.can_feed_brain,
                can_feed_paper = EXCLUDED.can_feed_paper,
                has_market_id = EXCLUDED.has_market_id,
                has_source = EXCLUDED.has_source,
                has_lineage = EXCLUDED.has_lineage,
                has_correlation_id = EXCLUDED.has_correlation_id,
                has_raw_payload_ref = EXCLUDED.has_raw_payload_ref,
                has_confidence = EXCLUDED.has_confidence,
                has_strength = EXCLUDED.has_strength,
                has_freshness = EXCLUDED.has_freshness,
                has_evidence = EXCLUDED.has_evidence,
                linked_to_market = EXCLUDED.linked_to_market,
                linked_to_position = EXCLUDED.linked_to_position,
                used_by_brain_output = EXCLUDED.used_by_brain_output,
                used_by_coordinator = EXCLUDED.used_by_coordinator,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_stale = EXCLUDED.is_stale,
                evaluated_at = EXCLUDED.evaluated_at,
                updated_at = now()
            RETURNING *
            """,
            params,
        ).fetchone()
        return dict(row)

    def get_evaluation(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM signal_quality_evaluations WHERE signal_id = %s",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_evaluations(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        quality_status: str | None = None,
        can_feed_brain: bool | None = None,
        can_feed_paper: bool | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if quality_status:
            filters.append("quality_status = %s")
            params.append(quality_status.strip().upper())
        if can_feed_brain is not None:
            filters.append("can_feed_brain = %s")
            params.append(can_feed_brain)
        if can_feed_paper is not None:
            filters.append("can_feed_paper = %s")
            params.append(can_feed_paper)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM signal_quality_evaluations
                {where}
                ORDER BY evaluated_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int = 20) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_evaluated,
                COALESCE(AVG(quality_score), 0) AS avg_quality_score,
                COUNT(*) FILTER (WHERE can_feed_brain IS TRUE) AS can_feed_brain,
                COUNT(*) FILTER (WHERE can_feed_paper IS TRUE) AS can_feed_paper,
                COUNT(*) FILTER (WHERE is_dry_run_generated IS TRUE) AS dry_run_generated,
                COUNT(*) FILTER (WHERE is_runtime_generated IS TRUE) AS runtime_generated,
                COUNT(*) FILTER (WHERE quality_score < 0.5 OR quality_status IN ('WEAK', 'BLOCKED', 'UNBOUND', 'UNLINKED', 'STALE', 'DRY_RUN_ONLY')) AS low_quality_count,
                MAX(evaluated_at) AS latest_evaluated_at
            FROM signal_quality_evaluations
            """
        ).fetchone()
        by_status = conn.execute(
            """
            SELECT quality_status, COUNT(*) AS count
            FROM signal_quality_evaluations
            GROUP BY quality_status
            ORDER BY count DESC, quality_status ASC
            """
        ).fetchall()
        missing_fields = conn.execute(
            """
            SELECT field, COUNT(*) AS count
            FROM signal_quality_evaluations,
                 jsonb_array_elements_text(missing_fields_json) AS field
            GROUP BY field
            ORDER BY count DESC, field ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        low_quality = conn.execute(
            """
            SELECT *
            FROM signal_quality_evaluations
            WHERE quality_score < 0.5
               OR quality_status IN ('WEAK', 'BLOCKED', 'UNBOUND', 'UNLINKED', 'STALE', 'DRY_RUN_ONLY')
            ORDER BY quality_score ASC, evaluated_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        paper_blockers = conn.execute(
            """
            SELECT field AS reason, COUNT(*) AS count
            FROM signal_quality_evaluations,
                 jsonb_array_elements_text(missing_fields_json) AS field
            WHERE can_feed_paper IS FALSE
            GROUP BY field
            ORDER BY count DESC, field ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return {
            "total_evaluated": int(totals["total_evaluated"] or 0),
            "avg_quality_score": round(float(totals["avg_quality_score"] or 0), 4),
            "can_feed_brain": int(totals["can_feed_brain"] or 0),
            "can_feed_paper": int(totals["can_feed_paper"] or 0),
            "quality_by_status": [dict(row) for row in by_status],
            "missing_fields_summary": [dict(row) for row in missing_fields],
            "dry_run_generated": int(totals["dry_run_generated"] or 0),
            "runtime_generated": int(totals["runtime_generated"] or 0),
            "low_quality_count": int(totals["low_quality_count"] or 0),
            "low_quality_signals": [dict(row) for row in low_quality],
            "paper_blocking_reasons": [dict(row) for row in paper_blockers],
            "latest_evaluated_at": totals["latest_evaluated_at"],
        }


def _evaluation_params(evaluation: SignalQualityEvaluation) -> dict[str, Any]:
    data = evaluation.model_dump()
    data["missing_fields_json"] = Jsonb(json.loads(json.dumps(data.pop("missing_fields", []) or [], default=str)))
    return data
