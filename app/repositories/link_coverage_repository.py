from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.link_coverage import SignalLinkCoverageAnalysis, SuggestedMarketLink


class LinkCoverageRepository:
    def get_signal_context(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.signal_id,
                s.neuron,
                s.event_type,
                s.source_name,
                s.market_id,
                s.correlation_id,
                s.status AS signal_status,
                s.evidence_json,
                s.raw_payload_ref,
                s.entity_count,
                s.evidence_count,
                s.created_at AS signal_created_at,
                s.stale_after_seconds,
                s.expires_at,
                EXISTS (SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id) AS linked_to_market,
                EXISTS (SELECT 1 FROM signal_position_links spl WHERE spl.signal_id = s.signal_id) AS linked_to_position,
                EXISTS (SELECT 1 FROM neuron_signal_entities ent WHERE ent.signal_id = s.signal_id) AS has_signal_entity,
                EXISTS (SELECT 1 FROM event_entities ent WHERE ent.source_signal_id = s.signal_id) AS has_event_entity,
                b.producer_name,
                b.source_name AS binding_source_name,
                b.generated_from,
                b.raw_payload_ref AS binding_raw_payload_ref,
                q.quality_status,
                q.is_dry_run_generated AS quality_is_dry_run_generated,
                q.is_runtime_generated AS quality_is_runtime_generated,
                q.is_stale AS quality_is_stale,
                q.can_feed_brain AS quality_can_feed_brain,
                q.can_feed_paper AS quality_can_feed_paper,
                ps.processing_state,
                ps.gate_status
            FROM neuron_signals s
            LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
            LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
            LEFT JOIN signal_processing_states ps ON ps.signal_id = s.signal_id
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

    def market_exists(self, conn: Connection, market_id: str) -> bool:
        checks = [
            ("markets_v2", "market_id"),
            ("market_snapshots_v2", "market_id"),
            ("market_snapshots", "market_id"),
        ]
        for table_name, column_name in checks:
            if not _table_exists(conn, table_name):
                continue
            row = conn.execute(f"SELECT 1 FROM {table_name} WHERE {column_name} = %s LIMIT 1", (market_id,)).fetchone()
            if row:
                return True
        return False

    def find_entity_market_candidate(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            WITH signal_entities AS (
                SELECT COALESCE(NULLIF(entity_id, ''), lower(entity_name)) AS entity_key
                FROM neuron_signal_entities
                WHERE signal_id = %s
                UNION
                SELECT COALESCE(NULLIF(entity_id, ''), lower(entity_name)) AS entity_key
                FROM event_entities
                WHERE source_signal_id = %s
            )
            SELECT eml.market_id, eml.confidence, eml.link_type, eml.link_status, eml.entity_id
            FROM entity_market_links eml
            JOIN event_entities ent ON ent.entity_id = eml.entity_id
            JOIN signal_entities se ON se.entity_key = COALESCE(NULLIF(ent.entity_id, ''), lower(ent.entity_name))
            WHERE eml.link_status IN ('confirmed', 'suggested')
            ORDER BY eml.confidence DESC NULLS LAST, eml.created_at DESC, eml.id DESC
            LIMIT 1
            """,
            (signal_id, signal_id),
        ).fetchone()
        return dict(row) if row else None

    def upsert_analysis(self, conn: Connection, analysis: SignalLinkCoverageAnalysis) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_link_coverage_analysis (
                signal_id, is_linked_to_market, is_linked_to_position, is_unlinked,
                linkability_status, primary_unlinked_reason, unlinked_reasons_json,
                missing_fields_json, has_market_id, has_entity, has_source,
                has_rules_context, has_producer, has_matcher_evidence,
                has_raw_payload_ref, is_dry_run_generated, is_runtime_generated,
                is_stale, suggested_market_id, suggested_market_confidence,
                suggested_market_reason, suggested_link_action, can_auto_link,
                can_feed_brain_after_link, can_feed_paper_after_link,
                analysis_status, analyzed_at, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(is_linked_to_market)s, %(is_linked_to_position)s,
                %(is_unlinked)s, %(linkability_status)s, %(primary_unlinked_reason)s,
                %(unlinked_reasons_json)s, %(missing_fields_json)s, %(has_market_id)s,
                %(has_entity)s, %(has_source)s, %(has_rules_context)s,
                %(has_producer)s, %(has_matcher_evidence)s, %(has_raw_payload_ref)s,
                %(is_dry_run_generated)s, %(is_runtime_generated)s, %(is_stale)s,
                %(suggested_market_id)s, %(suggested_market_confidence)s,
                %(suggested_market_reason)s, %(suggested_link_action)s,
                %(can_auto_link)s, %(can_feed_brain_after_link)s,
                %(can_feed_paper_after_link)s, %(analysis_status)s,
                COALESCE(%(analyzed_at)s, now()), now(), now()
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                is_linked_to_market = EXCLUDED.is_linked_to_market,
                is_linked_to_position = EXCLUDED.is_linked_to_position,
                is_unlinked = EXCLUDED.is_unlinked,
                linkability_status = EXCLUDED.linkability_status,
                primary_unlinked_reason = EXCLUDED.primary_unlinked_reason,
                unlinked_reasons_json = EXCLUDED.unlinked_reasons_json,
                missing_fields_json = EXCLUDED.missing_fields_json,
                has_market_id = EXCLUDED.has_market_id,
                has_entity = EXCLUDED.has_entity,
                has_source = EXCLUDED.has_source,
                has_rules_context = EXCLUDED.has_rules_context,
                has_producer = EXCLUDED.has_producer,
                has_matcher_evidence = EXCLUDED.has_matcher_evidence,
                has_raw_payload_ref = EXCLUDED.has_raw_payload_ref,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_stale = EXCLUDED.is_stale,
                suggested_market_id = EXCLUDED.suggested_market_id,
                suggested_market_confidence = EXCLUDED.suggested_market_confidence,
                suggested_market_reason = EXCLUDED.suggested_market_reason,
                suggested_link_action = EXCLUDED.suggested_link_action,
                can_auto_link = EXCLUDED.can_auto_link,
                can_feed_brain_after_link = EXCLUDED.can_feed_brain_after_link,
                can_feed_paper_after_link = EXCLUDED.can_feed_paper_after_link,
                analysis_status = EXCLUDED.analysis_status,
                analyzed_at = EXCLUDED.analyzed_at,
                updated_at = now()
            RETURNING *
            """,
            _analysis_params(analysis),
        ).fetchone()
        return dict(row)

    def upsert_suggestion(self, conn: Connection, suggestion: SuggestedMarketLink) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_suggested_market_links (
                signal_id, suggested_market_id, confidence, evidence_json, reason,
                suggestion_status, created_by, is_applied, applied_at, rejected_at,
                rejection_reason, created_at, updated_at
            )
            VALUES (
                %(signal_id)s, %(suggested_market_id)s, %(confidence)s,
                %(evidence_json)s, %(reason)s, %(suggestion_status)s,
                %(created_by)s, %(is_applied)s, %(applied_at)s, %(rejected_at)s,
                %(rejection_reason)s, now(), now()
            )
            ON CONFLICT (signal_id, suggested_market_id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence_json = EXCLUDED.evidence_json,
                reason = EXCLUDED.reason,
                suggestion_status = EXCLUDED.suggestion_status,
                created_by = EXCLUDED.created_by,
                updated_at = now()
            RETURNING *
            """,
            _suggestion_params(suggestion),
        ).fetchone()
        return dict(row)

    def apply_safe_signal_market_link(self, conn: Connection, *, signal_id: str, market_id: str, reason: str) -> bool:
        exists = conn.execute("SELECT 1 FROM signal_market_links WHERE signal_id = %s AND market_id = %s", (signal_id, market_id)).fetchone()
        if exists:
            return False
        conn.execute(
            """
            INSERT INTO signal_market_links (signal_id, market_id, link_type, link_status, confidence, reason, created_by)
            VALUES (%s, %s, 'exact_match', 'suggested', 0.95, %s, 'link_coverage_safe_apply')
            """,
            (signal_id, market_id, reason),
        )
        conn.execute(
            """
            UPDATE signal_suggested_market_links
            SET suggestion_status = 'APPLIED', is_applied = true, applied_at = now(), updated_at = now()
            WHERE signal_id = %s AND suggested_market_id = %s
            """,
            (signal_id, market_id),
        )
        return True

    def get_analysis(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM signal_link_coverage_analysis WHERE signal_id = %s", (signal_id,)).fetchone()
        return dict(row) if row else None

    def list_analyses(self, conn: Connection, *, limit: int = 50, linkability_status: str | None = None, reason: str | None = None) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if linkability_status:
            filters.append("linkability_status = %s")
            params.append(linkability_status.strip().upper())
        if reason:
            filters.append("primary_unlinked_reason = %s")
            params.append(reason.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM signal_link_coverage_analysis
                {where}
                ORDER BY analyzed_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def list_suggestions(self, conn: Connection, signal_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM signal_suggested_market_links
                WHERE signal_id = %s
                ORDER BY confidence DESC, created_at DESC, id DESC
                LIMIT %s
                """,
                (signal_id, limit),
            ).fetchall()
        ]

    def record_run(self, conn: Connection, *, requested_limit: int, summary: dict[str, Any], status: str, error_summary: str | None = None) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_link_coverage_runs (
                requested_limit, analyzed_count, linked_count, unlinked_count,
                linkable_count, non_linkable_count, suggested_count,
                safe_to_link_count, error_count, status, finished_at, error_summary
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
            RETURNING *
            """,
            (
                requested_limit,
                int(summary.get("analyzed_count") or 0),
                int(summary.get("linked_count") or 0),
                int(summary.get("unlinked_count") or 0),
                int(summary.get("linkable_count") or 0),
                int(summary.get("non_linkable_count") or 0),
                int(summary.get("suggested_count") or 0),
                int(summary.get("safe_to_link_count") or 0),
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
                COUNT(*) FILTER (WHERE is_linked_to_market OR is_linked_to_position) AS linked_signals,
                COUNT(*) FILTER (WHERE is_unlinked) AS unlinked_signals,
                COUNT(*) FILTER (WHERE linkability_status = 'LINKABLE') AS linkable_signals,
                COUNT(*) FILTER (WHERE linkability_status = 'NOT_LINKABLE') AS non_linkable_signals,
                COUNT(*) FILTER (WHERE linkability_status = 'NEEDS_MORE_EVIDENCE') AS needs_more_evidence,
                COUNT(*) FILTER (WHERE linkability_status = 'STALE') AS stale_unlinked,
                COUNT(*) FILTER (WHERE linkability_status = 'DRY_RUN_ONLY') AS dry_run_only_unlinked,
                COUNT(*) FILTER (WHERE can_auto_link) AS safe_to_link_count,
                MAX(analyzed_at) AS last_analysis_at,
                COUNT(*) FILTER (WHERE analysis_status = 'ERROR') AS error_count
            FROM signal_link_coverage_analysis
            """
        ).fetchone()
        by_reason = conn.execute(
            """
            SELECT primary_unlinked_reason, COUNT(*) AS count
            FROM signal_link_coverage_analysis
            GROUP BY primary_unlinked_reason
            ORDER BY count DESC, primary_unlinked_reason ASC
            """
        ).fetchall()
        suggestions = conn.execute(
            """
            SELECT
                COUNT(*) AS suggested_market_links_count,
                COUNT(*) FILTER (WHERE is_applied) AS applied_suggestions_count,
                COUNT(*) FILTER (WHERE suggestion_status = 'REJECTED_WEAK_EVIDENCE') AS weak_suggestions_count
            FROM signal_suggested_market_links
            """
        ).fetchone()
        latest = self.list_analyses(conn, limit=limit)
        return {
            "total_signals": int(totals["total_signals"] or 0),
            "total_analyzed": int(totals["total_analyzed"] or 0),
            "linked_signals": int(totals["linked_signals"] or 0),
            "unlinked_signals": int(totals["unlinked_signals"] or 0),
            "linkable_signals": int(totals["linkable_signals"] or 0),
            "non_linkable_signals": int(totals["non_linkable_signals"] or 0),
            "needs_more_evidence": int(totals["needs_more_evidence"] or 0),
            "stale_unlinked": int(totals["stale_unlinked"] or 0),
            "dry_run_only_unlinked": int(totals["dry_run_only_unlinked"] or 0),
            "safe_to_link_count": int(totals["safe_to_link_count"] or 0),
            "last_analysis_at": totals["last_analysis_at"],
            "error_count": int(totals["error_count"] or 0),
            "unlinked_by_reason": [dict(row) for row in by_reason],
            "suggested_market_links_count": int(suggestions["suggested_market_links_count"] or 0),
            "applied_suggestions_count": int(suggestions["applied_suggestions_count"] or 0),
            "weak_suggestions_count": int(suggestions["weak_suggestions_count"] or 0),
            "latest_analyses": latest,
        }


def _analysis_params(analysis: SignalLinkCoverageAnalysis) -> dict[str, Any]:
    data = analysis.model_dump()
    data["unlinked_reasons_json"] = Jsonb(json.loads(json.dumps(data.pop("unlinked_reasons", []) or [], default=str)))
    data["missing_fields_json"] = Jsonb(json.loads(json.dumps(data.pop("missing_fields", []) or [], default=str)))
    return data


def _suggestion_params(suggestion: SuggestedMarketLink) -> dict[str, Any]:
    data = suggestion.model_dump()
    data["evidence_json"] = Jsonb(json.loads(json.dumps(data.pop("evidence", {}) or {}, default=str)))
    return data


def _table_exists(conn: Connection, table_name: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table_name,)).fetchone()
    return bool(row and row["table_name"])
