from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.signal_market_binding import SignalMarketBindingCandidate, SignalMarketBindingRun


class SignalMarketBindingRepository:
    def list_unlinked_signal_contexts(
        self,
        conn: Connection,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
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
                    s.status AS signal_status,
                    s.evidence_json,
                    s.raw_payload_ref,
                    s.created_at,
                    s.expires_at,
                    s.stale_after_seconds,
                    b.producer_name,
                    b.source_name AS binding_source_name,
                    b.generated_from,
                    b.raw_payload_ref AS binding_raw_payload_ref,
                    b.lineage_json,
                    q.quality_score,
                    q.quality_status,
                    q.is_dry_run_generated AS quality_is_dry_run_generated,
                    q.is_runtime_generated AS quality_is_runtime_generated,
                    q.is_stale AS quality_is_stale,
                    ps.processing_state,
                    ps.gate_status,
                    lca.linkability_status,
                    lca.primary_unlinked_reason,
                    lca.is_stale AS link_coverage_is_stale
                FROM neuron_signals s
                LEFT JOIN neuron_signal_bindings b ON b.signal_id = s.signal_id
                LEFT JOIN signal_quality_evaluations q ON q.signal_id = s.signal_id
                LEFT JOIN signal_processing_states ps ON ps.signal_id = s.signal_id
                LEFT JOIN signal_link_coverage_analysis lca ON lca.signal_id = s.signal_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id
                )
                ORDER BY s.created_at DESC, s.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def market_by_id(self, conn: Connection, market_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM markets_v2 WHERE market_id = %s LIMIT 1", (market_id,)).fetchone()
        return dict(row) if row else None

    def markets_by_token_id(self, conn: Connection, token_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *,
                    CASE
                        WHEN yes_token_id = %s THEN 'YES'
                        WHEN no_token_id = %s THEN 'NO'
                        ELSE NULL
                    END AS matched_side
                FROM markets_v2
                WHERE yes_token_id = %s OR no_token_id = %s
                ORDER BY last_seen_at DESC NULLS LAST, id DESC
                """,
                (token_id, token_id, token_id, token_id),
            ).fetchall()
        ]

    def markets_by_condition_id(self, conn: Connection, condition_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM markets_v2
                WHERE condition_id = %s
                ORDER BY last_seen_at DESC NULLS LAST, id DESC
                """,
                (condition_id,),
            ).fetchall()
        ]

    def markets_by_slug(self, conn: Connection, slug: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM markets_v2
                WHERE lower(slug) = lower(%s)
                ORDER BY last_seen_at DESC NULLS LAST, id DESC
                """,
                (slug,),
            ).fetchall()
        ]

    def apply_link(
        self,
        conn: Connection,
        *,
        signal_id: str,
        market_id: str,
        confidence: float,
        reason: str,
        evidence: dict[str, Any],
        method: str,
        runtime_link: bool,
    ) -> bool:
        exists = conn.execute(
            "SELECT 1 FROM signal_market_links WHERE signal_id = %s AND market_id = %s LIMIT 1",
            (signal_id, market_id),
        ).fetchone()
        if exists:
            return False
        matched_side = _valid_side(evidence.get("matched_side"))
        side_resolved_at = datetime.now(UTC) if matched_side else None
        conn.execute(
            """
            INSERT INTO signal_market_links (
                signal_id, market_id, link_type, link_status, confidence, reason,
                created_by, link_confidence, link_reason, link_evidence_json,
                link_method, linked_by, is_auto_linked, is_review_required,
                is_runtime_link, source_signal_id, matched_side, side_source,
                side_source_id, side_confidence, side_evidence_json, side_resolved_at
            )
            VALUES (
                %s, %s, %s, 'confirmed', %s, %s, 'signal_market_binding_recovery',
                %s, %s, %s, %s, 'signal_market_binding_recovery', TRUE, FALSE, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                signal_id,
                market_id,
                method,
                confidence,
                reason,
                confidence,
                reason,
                Jsonb(_jsonable(evidence)),
                method,
                runtime_link,
                signal_id,
                matched_side,
                "token_id" if matched_side else None,
                _side_source_id(evidence) if matched_side else None,
                confidence if matched_side else None,
                Jsonb(_jsonable({"source": "signal_market_binding_recovery", **evidence}) if matched_side else {}),
                side_resolved_at,
            ),
        )
        conn.execute(
            """
            UPDATE signal_suggested_market_links
            SET suggestion_status = 'APPLIED',
                is_applied = true,
                applied_at = now(),
                updated_at = now()
            WHERE signal_id = %s AND suggested_market_id = %s
            """,
            (signal_id, market_id),
        )
        return True

    def upsert_suggestion(
        self,
        conn: Connection,
        *,
        signal_id: str,
        market_id: str,
        confidence: float,
        reason: str,
        evidence: dict[str, Any],
        status: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO signal_suggested_market_links (
                signal_id, suggested_market_id, confidence, evidence_json, reason,
                suggestion_status, created_by, is_applied, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'signal_market_binding_recovery', FALSE, now(), now())
            ON CONFLICT (signal_id, suggested_market_id) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                evidence_json = EXCLUDED.evidence_json,
                reason = EXCLUDED.reason,
                suggestion_status = EXCLUDED.suggestion_status,
                created_by = EXCLUDED.created_by,
                updated_at = now()
            """,
            (signal_id, market_id, confidence, Jsonb(_jsonable(evidence)), reason, status),
        )

    def record_candidate(self, conn: Connection, *, run_id: str, candidate: SignalMarketBindingCandidate) -> None:
        conn.execute(
            """
            INSERT INTO signal_market_binding_candidates (
                run_id, signal_id, candidate_market_id, confidence, evidence_json, reason, action, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            """,
            (
                run_id,
                candidate.signal_id,
                candidate.candidate_market_id,
                candidate.confidence,
                Jsonb(_jsonable(candidate.evidence)),
                candidate.reason,
                candidate.action,
            ),
        )

    def record_run(self, conn: Connection, run: SignalMarketBindingRun) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_market_binding_recovery_runs (
                run_id, status, signals_checked, runtime_signals_checked, already_linked,
                safe_links_created, suggestions_created, remained_unlinked,
                stale_skipped, dry_run_skipped, weak_evidence_skipped,
                ambiguous_candidates, signal_market_links_before,
                signal_market_links_after, paper_ready_before, paper_ready_after,
                orders_created, order_intents_created, fills_created, positions_created,
                live_actions_created, started_at, finished_at, error_summary, created_at
            )
            VALUES (
                %(run_id)s, %(status)s, %(signals_checked)s, %(runtime_signals_checked)s,
                %(already_linked)s, %(safe_links_created)s, %(suggestions_created)s,
                %(remained_unlinked)s, %(stale_skipped)s, %(dry_run_skipped)s,
                %(weak_evidence_skipped)s, %(ambiguous_candidates)s,
                %(signal_market_links_before)s, %(signal_market_links_after)s,
                %(paper_ready_before)s, %(paper_ready_after)s, %(orders_created)s,
                %(order_intents_created)s, %(fills_created)s, %(positions_created)s,
                %(live_actions_created)s, %(started_at)s, %(finished_at)s,
                %(error_summary)s, now()
            )
            RETURNING *
            """,
            run.model_dump(exclude={"mock_data", "candidates"}),
        ).fetchone()
        return dict(row)

    def latest_run(self, conn: Connection) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM signal_market_binding_recovery_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None

    def list_latest_candidates(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM signal_market_binding_candidates
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int = 50) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM neuron_signals) AS total_signals,
                (SELECT COUNT(*) FROM neuron_signals s WHERE s.evidence_json->>'generated_by' = 'runtime' OR s.evidence_json->>'is_runtime_generated' = 'true') AS runtime_signals,
                (SELECT COUNT(*) FROM signal_market_links) AS signal_market_links,
                (SELECT COUNT(DISTINCT s.signal_id)
                 FROM neuron_signals s
                 JOIN signal_market_links sml ON sml.signal_id = s.signal_id
                 WHERE s.evidence_json->>'generated_by' = 'runtime' OR s.evidence_json->>'is_runtime_generated' = 'true') AS linked_runtime_signals,
                (SELECT COUNT(*)
                 FROM neuron_signals s
                 WHERE (s.evidence_json->>'generated_by' = 'runtime' OR s.evidence_json->>'is_runtime_generated' = 'true')
                   AND NOT EXISTS (SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id)) AS unlinked_runtime_signals
            """
        ).fetchone()
        latest_run = self.latest_run(conn)
        candidates = self.list_latest_candidates(conn, limit=limit)
        by_action = conn.execute(
            """
            SELECT action, COUNT(*) AS count
            FROM signal_market_binding_candidates
            GROUP BY action
            ORDER BY count DESC, action ASC
            """
        ).fetchall()
        return {
            "total_signals": int(totals["total_signals"] or 0),
            "runtime_signals": int(totals["runtime_signals"] or 0),
            "signal_market_links": int(totals["signal_market_links"] or 0),
            "linked_runtime_signals": int(totals["linked_runtime_signals"] or 0),
            "unlinked_runtime_signals": int(totals["unlinked_runtime_signals"] or 0),
            "latest_run": latest_run,
            "latest_candidates": candidates,
            "by_action": [dict(row) for row in by_action],
        }


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value or {}, default=str))


def _valid_side(value: Any) -> str | None:
    side = str(value or "").strip().upper()
    return side if side in {"YES", "NO"} else None


def _side_source_id(evidence: dict[str, Any]) -> str | None:
    token_ids = evidence.get("token_ids")
    if isinstance(token_ids, list) and token_ids:
        return str(token_ids[0])
    value = evidence.get("token_id") or evidence.get("sample_token_id") or evidence.get("asset_id")
    return str(value) if value else None
