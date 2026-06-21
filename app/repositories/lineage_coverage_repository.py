from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.lineage_coverage import SignalLineageCoverageAnalysis


class LineageCoverageRepository:
    def get_signal_context(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.signal_id,
                s.neuron,
                s.event_type,
                s.source_name,
                s.correlation_id,
                s.raw_payload_ref,
                s.status AS signal_status,
                s.evidence_json,
                s.created_at AS signal_created_at,
                s.updated_at AS signal_updated_at,
                s.expires_at,
                s.stale_after_seconds,
                b.id AS binding_id,
                b.producer_name,
                b.producer_component,
                b.producer_version,
                b.source_name AS binding_source_name,
                b.source_status_id,
                b.event_log_id,
                b.source_event_id,
                b.correlation_id AS binding_correlation_id,
                b.raw_payload_ref AS binding_raw_payload_ref,
                b.generated_from,
                b.lineage_json,
                b.created_at AS binding_created_at,
                q.is_dry_run_generated AS quality_is_dry_run_generated,
                q.is_runtime_generated AS quality_is_runtime_generated,
                q.is_stale AS quality_is_stale
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
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

    def upsert_analysis(self, conn: Connection, analysis: SignalLineageCoverageAnalysis) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_lineage_coverage_analysis (
                signal_id, lineage_status, lineage_trust_score, is_bound,
                is_unbound, primary_unbound_reason, unbound_reasons_json,
                missing_lineage_fields_json, producer, source, correlation_id,
                raw_payload_ref, generated_from, generated_by, generated_at,
                signal_created_at, is_dry_run_generated, is_runtime_generated,
                is_manual_generated, is_adapter_generated, has_producer,
                has_source, has_correlation_id, has_raw_payload_ref,
                has_generated_from, has_generated_at, has_explainable_origin,
                can_trace_to_event, can_trace_to_payload, can_trace_to_producer,
                can_feed_brain_by_lineage, can_feed_paper_by_lineage,
                analysis_status, analysis_error, analyzed_at, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(lineage_status)s, %(lineage_trust_score)s,
                %(is_bound)s, %(is_unbound)s, %(primary_unbound_reason)s,
                %(unbound_reasons_json)s, %(missing_lineage_fields_json)s,
                %(producer)s, %(source)s, %(correlation_id)s, %(raw_payload_ref)s,
                %(generated_from)s, %(generated_by)s, %(generated_at)s,
                %(signal_created_at)s, %(is_dry_run_generated)s,
                %(is_runtime_generated)s, %(is_manual_generated)s,
                %(is_adapter_generated)s, %(has_producer)s, %(has_source)s,
                %(has_correlation_id)s, %(has_raw_payload_ref)s,
                %(has_generated_from)s, %(has_generated_at)s,
                %(has_explainable_origin)s, %(can_trace_to_event)s,
                %(can_trace_to_payload)s, %(can_trace_to_producer)s,
                %(can_feed_brain_by_lineage)s, %(can_feed_paper_by_lineage)s,
                %(analysis_status)s, %(analysis_error)s,
                COALESCE(%(analyzed_at)s, now()), now(), now()
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                lineage_status = EXCLUDED.lineage_status,
                lineage_trust_score = EXCLUDED.lineage_trust_score,
                is_bound = EXCLUDED.is_bound,
                is_unbound = EXCLUDED.is_unbound,
                primary_unbound_reason = EXCLUDED.primary_unbound_reason,
                unbound_reasons_json = EXCLUDED.unbound_reasons_json,
                missing_lineage_fields_json = EXCLUDED.missing_lineage_fields_json,
                producer = EXCLUDED.producer,
                source = EXCLUDED.source,
                correlation_id = EXCLUDED.correlation_id,
                raw_payload_ref = EXCLUDED.raw_payload_ref,
                generated_from = EXCLUDED.generated_from,
                generated_by = EXCLUDED.generated_by,
                generated_at = EXCLUDED.generated_at,
                signal_created_at = EXCLUDED.signal_created_at,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_manual_generated = EXCLUDED.is_manual_generated,
                is_adapter_generated = EXCLUDED.is_adapter_generated,
                has_producer = EXCLUDED.has_producer,
                has_source = EXCLUDED.has_source,
                has_correlation_id = EXCLUDED.has_correlation_id,
                has_raw_payload_ref = EXCLUDED.has_raw_payload_ref,
                has_generated_from = EXCLUDED.has_generated_from,
                has_generated_at = EXCLUDED.has_generated_at,
                has_explainable_origin = EXCLUDED.has_explainable_origin,
                can_trace_to_event = EXCLUDED.can_trace_to_event,
                can_trace_to_payload = EXCLUDED.can_trace_to_payload,
                can_trace_to_producer = EXCLUDED.can_trace_to_producer,
                can_feed_brain_by_lineage = EXCLUDED.can_feed_brain_by_lineage,
                can_feed_paper_by_lineage = EXCLUDED.can_feed_paper_by_lineage,
                analysis_status = EXCLUDED.analysis_status,
                analysis_error = EXCLUDED.analysis_error,
                analyzed_at = EXCLUDED.analyzed_at,
                updated_at = now()
            RETURNING *
            """,
            _analysis_params(analysis),
        ).fetchone()
        return dict(row)

    def get_analysis(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM signal_lineage_coverage_analysis WHERE signal_id = %s", (signal_id,)).fetchone()
        return dict(row) if row else None

    def list_analyses(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        lineage_status: str | None = None,
        reason: str | None = None,
        producer: str | None = None,
        source: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if lineage_status:
            filters.append("lineage_status = %s")
            params.append(lineage_status.strip().upper())
        if reason:
            filters.append("primary_unbound_reason = %s")
            params.append(reason.strip().upper())
        if producer:
            filters.append("producer = %s")
            params.append(producer)
        if source:
            filters.append("source = %s")
            params.append(source)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM signal_lineage_coverage_analysis
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
            INSERT INTO signal_lineage_coverage_runs (
                requested_limit, analyzed_count, bound_count, unbound_count,
                complete_count, partial_count, dry_run_only_count,
                runtime_verified_count, missing_producer_count,
                missing_source_count, missing_correlation_id_count,
                missing_raw_payload_ref_count, missing_generated_from_count,
                error_count, status, finished_at, error_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
            RETURNING *
            """,
            (
                requested_limit,
                int(summary.get("analyzed_count") or summary.get("total_analyzed") or 0),
                int(summary.get("bound_count") or summary.get("bound_signals") or 0),
                int(summary.get("unbound_count") or summary.get("unbound_signals") or 0),
                int(summary.get("complete_count") or summary.get("complete_lineage") or 0),
                int(summary.get("partial_count") or summary.get("partial_lineage") or 0),
                int(summary.get("dry_run_only_count") or summary.get("dry_run_only_signals") or 0),
                int(summary.get("runtime_verified_count") or summary.get("runtime_verified_signals") or 0),
                int(summary.get("missing_producer_count") or 0),
                int(summary.get("missing_source_count") or 0),
                int(summary.get("missing_correlation_id_count") or 0),
                int(summary.get("missing_raw_payload_ref_count") or 0),
                int(summary.get("missing_generated_from_count") or 0),
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
                (SELECT COUNT(*) FROM neuron_signals) AS total_signals,
                COUNT(*) AS total_analyzed,
                COUNT(*) FILTER (WHERE is_bound) AS bound_signals,
                COUNT(*) FILTER (WHERE is_unbound) AS unbound_signals,
                COUNT(*) FILTER (WHERE lineage_status = 'COMPLETE') AS complete_lineage,
                COUNT(*) FILTER (WHERE lineage_status = 'PARTIAL') AS partial_lineage,
                COUNT(*) FILTER (WHERE lineage_status = 'DRY_RUN_ONLY') AS dry_run_only_signals,
                COUNT(*) FILTER (WHERE lineage_status = 'RUNTIME_VERIFIED') AS runtime_verified_signals,
                COUNT(*) FILTER (WHERE NOT has_producer) AS missing_producer_count,
                COUNT(*) FILTER (WHERE NOT has_source) AS missing_source_count,
                COUNT(*) FILTER (WHERE NOT has_correlation_id) AS missing_correlation_id_count,
                COUNT(*) FILTER (WHERE NOT has_raw_payload_ref) AS missing_raw_payload_ref_count,
                COUNT(*) FILTER (WHERE NOT has_generated_from) AS missing_generated_from_count,
                COUNT(*) FILTER (WHERE analysis_status = 'ERROR') AS error_count,
                AVG(lineage_trust_score) AS avg_lineage_trust_score,
                MAX(analyzed_at) AS last_analysis_at
            FROM signal_lineage_coverage_analysis
            """
        ).fetchone()
        by_reason = conn.execute(
            """
            SELECT primary_unbound_reason, COUNT(*) AS count
            FROM signal_lineage_coverage_analysis
            GROUP BY primary_unbound_reason
            ORDER BY count DESC, primary_unbound_reason ASC
            """
        ).fetchall()
        missing_fields = conn.execute(
            """
            SELECT field AS missing_field, COUNT(*) AS count
            FROM signal_lineage_coverage_analysis,
                 jsonb_array_elements_text(missing_lineage_fields_json) AS field
            GROUP BY field
            ORDER BY count DESC, field ASC
            """
        ).fetchall()
        producer_coverage = conn.execute(
            """
            SELECT COALESCE(producer, 'missing') AS producer, COUNT(*) AS count, MAX(analyzed_at) AS latest_at
            FROM signal_lineage_coverage_analysis
            GROUP BY COALESCE(producer, 'missing')
            ORDER BY count DESC, producer ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        source_coverage = conn.execute(
            """
            SELECT COALESCE(source, 'missing') AS source, COUNT(*) AS count, MAX(analyzed_at) AS latest_at
            FROM signal_lineage_coverage_analysis
            GROUP BY COALESCE(source, 'missing')
            ORDER BY count DESC, source ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest = self.list_analyses(conn, limit=limit)
        total_analyzed = int(totals["total_analyzed"] or 0)
        raw_count = int(totals["total_analyzed"] or 0) - int(totals["missing_raw_payload_ref_count"] or 0)
        corr_count = int(totals["total_analyzed"] or 0) - int(totals["missing_correlation_id_count"] or 0)
        producer_count = int(totals["total_analyzed"] or 0) - int(totals["missing_producer_count"] or 0)
        source_count = int(totals["total_analyzed"] or 0) - int(totals["missing_source_count"] or 0)
        return {
            "total_signals": int(totals["total_signals"] or 0),
            "total_analyzed": total_analyzed,
            "bound_signals": int(totals["bound_signals"] or 0),
            "unbound_signals": int(totals["unbound_signals"] or 0),
            "complete_lineage": int(totals["complete_lineage"] or 0),
            "partial_lineage": int(totals["partial_lineage"] or 0),
            "dry_run_only_signals": int(totals["dry_run_only_signals"] or 0),
            "runtime_verified_signals": int(totals["runtime_verified_signals"] or 0),
            "missing_producer_count": int(totals["missing_producer_count"] or 0),
            "missing_source_count": int(totals["missing_source_count"] or 0),
            "missing_correlation_id_count": int(totals["missing_correlation_id_count"] or 0),
            "missing_raw_payload_ref_count": int(totals["missing_raw_payload_ref_count"] or 0),
            "missing_generated_from_count": int(totals["missing_generated_from_count"] or 0),
            "error_count": int(totals["error_count"] or 0),
            "avg_lineage_trust_score": round(float(totals["avg_lineage_trust_score"] or 0.0), 4),
            "last_analysis_at": totals["last_analysis_at"],
            "unbound_by_reason": [dict(row) for row in by_reason],
            "missing_lineage_fields": [dict(row) for row in missing_fields],
            "producer_coverage": [dict(row) for row in producer_coverage],
            "source_coverage": [dict(row) for row in source_coverage],
            "raw_payload_coverage": _coverage(raw_count, total_analyzed),
            "correlation_coverage": _coverage(corr_count, total_analyzed),
            "producer_coverage_ratio": _ratio(producer_count, total_analyzed),
            "source_coverage_ratio": _ratio(source_count, total_analyzed),
            "latest_analyses": latest,
        }


def _analysis_params(analysis: SignalLineageCoverageAnalysis) -> dict[str, Any]:
    data = analysis.model_dump()
    data["unbound_reasons_json"] = Jsonb(json.loads(json.dumps(data.pop("unbound_reasons", []) or [], default=str)))
    data["missing_lineage_fields_json"] = Jsonb(json.loads(json.dumps(data.pop("missing_lineage_fields", []) or [], default=str)))
    return data


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _coverage(count: int, total: int) -> dict[str, Any]:
    return {"present": count, "missing": max(total - count, 0), "ratio": _ratio(count, total)}
