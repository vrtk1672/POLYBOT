from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.signal_processing import SignalProcessingState


class SignalProcessingRepository:
    def get_signal_processing_context(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT
                s.signal_id,
                s.market_id,
                s.correlation_id,
                s.created_at AS signal_created_at,
                EXISTS (SELECT 1 FROM signal_market_links sml WHERE sml.signal_id = s.signal_id) AS linked_to_market,
                EXISTS (SELECT 1 FROM signal_position_links spl WHERE spl.signal_id = s.signal_id) AS linked_to_position,
                EXISTS (
                    SELECT 1 FROM brain_output_dependencies dep
                    WHERE dep.dependency_type = 'signal'
                      AND dep.dependency_id = s.signal_id
                ) AS used_by_brain_output,
                EXISTS (
                    SELECT 1
                    FROM brain_output_dependencies dep
                    JOIN coordinator_decision_inputs cdi ON cdi.brain_output_id = dep.brain_output_id
                    WHERE dep.dependency_type = 'signal'
                      AND dep.dependency_id = s.signal_id
                ) AS used_by_coordinator,
                q.id AS quality_evaluation_id,
                q.quality_score,
                q.quality_status,
                q.missing_fields_json,
                q.readiness_reason,
                q.can_feed_brain,
                q.can_feed_paper,
                q.linked_to_market AS quality_linked_to_market,
                q.linked_to_position AS quality_linked_to_position,
                q.used_by_brain_output AS quality_used_by_brain_output,
                q.used_by_coordinator AS quality_used_by_coordinator,
                q.is_dry_run_generated,
                q.is_runtime_generated,
                q.is_stale,
                q.evaluated_at,
                ps.processing_state AS existing_processing_state,
                ps.gate_status AS existing_gate_status,
                ps.ignored_reason AS existing_ignored_reason,
                ps.error_reason AS existing_error_reason
            FROM neuron_signals s
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

    def upsert_state(self, conn: Connection, state: SignalProcessingState, *, actor: str = "signal_processing_gate") -> dict[str, Any]:
        existing = self.get_state(conn, state.signal_id)
        previous_state = existing["processing_state"] if existing else None
        previous_gate = existing["gate_status"] if existing else None
        params = _state_params(state)
        params["previous_state"] = previous_state
        row = conn.execute(
            """
            INSERT INTO signal_processing_states (
                signal_id, processing_state, previous_state, quality_evaluation_id,
                quality_score, quality_status, gate_status, gate_blockers_json,
                missing_requirements_json, linked_to_market, linked_to_position,
                used_by_brain_output, used_by_coordinator, is_dry_run_generated,
                is_runtime_generated, is_stale, can_feed_brain, can_feed_paper,
                rejection_reason, ignored_reason, error_reason, evaluated_at,
                first_seen_at, last_seen_at, updated_at, created_at
            )
            VALUES (
                %(signal_id)s, %(processing_state)s, %(previous_state)s,
                %(quality_evaluation_id)s, %(quality_score)s, %(quality_status)s,
                %(gate_status)s, %(gate_blockers_json)s, %(missing_requirements_json)s,
                %(linked_to_market)s, %(linked_to_position)s, %(used_by_brain_output)s,
                %(used_by_coordinator)s, %(is_dry_run_generated)s, %(is_runtime_generated)s,
                %(is_stale)s, %(can_feed_brain)s, %(can_feed_paper)s, %(rejection_reason)s,
                %(ignored_reason)s, %(error_reason)s, %(evaluated_at)s, now(), now(), now(), now()
            )
            ON CONFLICT (signal_id) DO UPDATE SET
                previous_state = signal_processing_states.processing_state,
                processing_state = EXCLUDED.processing_state,
                quality_evaluation_id = EXCLUDED.quality_evaluation_id,
                quality_score = EXCLUDED.quality_score,
                quality_status = EXCLUDED.quality_status,
                gate_status = EXCLUDED.gate_status,
                gate_blockers_json = EXCLUDED.gate_blockers_json,
                missing_requirements_json = EXCLUDED.missing_requirements_json,
                linked_to_market = EXCLUDED.linked_to_market,
                linked_to_position = EXCLUDED.linked_to_position,
                used_by_brain_output = EXCLUDED.used_by_brain_output,
                used_by_coordinator = EXCLUDED.used_by_coordinator,
                is_dry_run_generated = EXCLUDED.is_dry_run_generated,
                is_runtime_generated = EXCLUDED.is_runtime_generated,
                is_stale = EXCLUDED.is_stale,
                can_feed_brain = EXCLUDED.can_feed_brain,
                can_feed_paper = EXCLUDED.can_feed_paper,
                rejection_reason = EXCLUDED.rejection_reason,
                ignored_reason = EXCLUDED.ignored_reason,
                error_reason = EXCLUDED.error_reason,
                evaluated_at = EXCLUDED.evaluated_at,
                last_seen_at = now(),
                updated_at = now()
            RETURNING *
            """,
            params,
        ).fetchone()
        created = dict(row)
        if previous_state != created["processing_state"] or previous_gate != created["gate_status"]:
            self.insert_history(
                conn,
                signal_id=state.signal_id,
                old_state=previous_state,
                new_state=created["processing_state"],
                old_gate_status=previous_gate,
                new_gate_status=created["gate_status"],
                reason=_history_reason(state),
                actor=actor,
                correlation_id=None,
            )
        return created

    def insert_history(
        self,
        conn: Connection,
        *,
        signal_id: str,
        old_state: str | None,
        new_state: str,
        old_gate_status: str | None,
        new_gate_status: str,
        reason: str | None,
        actor: str | None,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO signal_processing_state_history (
                signal_id, old_state, new_state, old_gate_status, new_gate_status,
                reason, actor, correlation_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (signal_id, old_state, new_state, old_gate_status, new_gate_status, reason, actor, correlation_id),
        ).fetchone()
        return dict(row)

    def get_state(self, conn: Connection, signal_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM signal_processing_states WHERE signal_id = %s",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_states(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        state: str | None = None,
        gate_status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if state:
            filters.append("processing_state = %s")
            params.append(state.strip().upper())
        if gate_status:
            filters.append("gate_status = %s")
            params.append(gate_status.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM signal_processing_states
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                params,
            ).fetchall()
        ]

    def list_history(self, conn: Connection, signal_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM signal_processing_state_history
                WHERE signal_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (signal_id, limit),
            ).fetchall()
        ]

    def summary(self, conn: Connection, *, limit: int = 20) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE gate_status = 'NOT_EVALUATED') AS unprocessed_count,
                COUNT(*) FILTER (WHERE processing_state = 'QUALITY_CHECKED') AS quality_checked_count,
                COUNT(*) FILTER (WHERE processing_state = 'BRAIN_USED') AS brain_used_count,
                COUNT(*) FILTER (WHERE processing_state = 'COORDINATOR_USED') AS coordinator_used_count,
                COUNT(*) FILTER (WHERE processing_state = 'STALE') AS stale_count,
                COUNT(*) FILTER (WHERE processing_state = 'REJECTED') AS rejected_count,
                COUNT(*) FILTER (WHERE processing_state = 'ERROR') AS error_count,
                COUNT(*) FILTER (WHERE gate_status = 'BRAIN_ELIGIBLE') AS brain_eligible_count,
                COUNT(*) FILTER (WHERE gate_status = 'PAPER_ELIGIBLE_INFORMATIONAL_ONLY') AS paper_eligible_informational_count,
                MAX(updated_at) AS last_updated
            FROM signal_processing_states
            """
        ).fetchone()
        by_state = conn.execute(
            """
            SELECT processing_state, COUNT(*) AS count
            FROM signal_processing_states
            GROUP BY processing_state
            ORDER BY count DESC, processing_state ASC
            """
        ).fetchall()
        by_gate = conn.execute(
            """
            SELECT gate_status, COUNT(*) AS count
            FROM signal_processing_states
            GROUP BY gate_status
            ORDER BY count DESC, gate_status ASC
            """
        ).fetchall()
        blockers = conn.execute(
            """
            SELECT blocker, COUNT(*) AS count
            FROM signal_processing_states,
                 jsonb_array_elements_text(gate_blockers_json) AS blocker
            GROUP BY blocker
            ORDER BY count DESC, blocker ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        latest = self.list_states(conn, limit=limit)
        return {
            "total": int(totals["total"] or 0),
            "unprocessed_count": int(totals["unprocessed_count"] or 0),
            "quality_checked_count": int(totals["quality_checked_count"] or 0),
            "brain_used_count": int(totals["brain_used_count"] or 0),
            "coordinator_used_count": int(totals["coordinator_used_count"] or 0),
            "stale_count": int(totals["stale_count"] or 0),
            "rejected_count": int(totals["rejected_count"] or 0),
            "error_count": int(totals["error_count"] or 0),
            "brain_eligible_count": int(totals["brain_eligible_count"] or 0),
            "paper_eligible_informational_count": int(totals["paper_eligible_informational_count"] or 0),
            "last_updated": totals["last_updated"],
            "by_state": [dict(row) for row in by_state],
            "by_gate_status": [dict(row) for row in by_gate],
            "top_gate_blockers": [dict(row) for row in blockers],
            "latest_states": latest,
        }


def _state_params(state: SignalProcessingState) -> dict[str, Any]:
    data = state.model_dump()
    data["gate_blockers_json"] = Jsonb(json.loads(json.dumps(data.pop("gate_blockers", []) or [], default=str)))
    data["missing_requirements_json"] = Jsonb(json.loads(json.dumps(data.pop("missing_requirements", []) or [], default=str)))
    return data


def _history_reason(state: SignalProcessingState) -> str:
    if state.error_reason:
        return state.error_reason
    if state.ignored_reason:
        return state.ignored_reason
    if state.rejection_reason:
        return state.rejection_reason
    if state.gate_blockers:
        return ", ".join(state.gate_blockers[:5])
    return state.processing_state
