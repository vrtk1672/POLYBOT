from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.coordinator import CoordinatorDecision, CoordinatorDecisionConflict, CoordinatorDecisionInput


class CoordinatorRepository:
    def create_decision(self, conn: Connection, decision: CoordinatorDecision) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO coordinator_decisions (
                coordinator_decision_id, market_id, position_id, final_state, primary_reason,
                confidence, urgency, conflicts_detected, governor_required, execution_allowed,
                approved_actions_json, blocked_actions_json, required_reviews_json, risk_flags_json,
                source_brain_count, input_output_count, conflict_count, correlation_id, ttl_seconds,
                expires_at, status, metadata_json, created_at, updated_at
            )
            VALUES (
                %(coordinator_decision_id)s, %(market_id)s, %(position_id)s, %(final_state)s,
                %(primary_reason)s, %(confidence)s, %(urgency)s, %(conflicts_detected)s,
                %(governor_required)s, false, %(approved_actions_json)s, %(blocked_actions_json)s,
                %(required_reviews_json)s, %(risk_flags_json)s, %(source_brain_count)s,
                %(input_output_count)s, %(conflict_count)s, %(correlation_id)s, %(ttl_seconds)s,
                %(expires_at)s, %(status)s, %(metadata_json)s, COALESCE(%(created_at)s, now()),
                COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _decision_params(decision),
        ).fetchone()
        return dict(row)

    def add_input(self, conn: Connection, item: CoordinatorDecisionInput) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO coordinator_decision_inputs (
                coordinator_decision_id, brain_output_id, brain, input_role,
                input_recommendation, input_confidence, created_at
            )
            VALUES (
                %(coordinator_decision_id)s, %(brain_output_id)s, %(brain)s, %(input_role)s,
                %(input_recommendation)s, %(input_confidence)s, COALESCE(%(created_at)s, now())
            )
            RETURNING *
            """,
            item.model_dump(),
        ).fetchone()
        return dict(row)

    def add_conflict(self, conn: Connection, conflict: CoordinatorDecisionConflict) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO coordinator_decision_conflicts (
                coordinator_decision_id, conflict_type, conflict_key, conflict_reason,
                conflict_severity, left_brain, right_brain, left_output_id, right_output_id, created_at
            )
            VALUES (
                %(coordinator_decision_id)s, %(conflict_type)s, %(conflict_key)s,
                %(conflict_reason)s, %(conflict_severity)s, %(left_brain)s, %(right_brain)s,
                %(left_output_id)s, %(right_output_id)s, COALESCE(%(created_at)s, now())
            )
            RETURNING *
            """,
            conflict.model_dump(),
        ).fetchone()
        return dict(row)

    def get_decision(self, conn: Connection, coordinator_decision_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM coordinator_decisions WHERE coordinator_decision_id = %s",
            (coordinator_decision_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_inputs(self, conn: Connection, coordinator_decision_id: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT coordinator_decision_id, brain_output_id, brain, input_role,
                   input_recommendation, input_confidence, created_at
            FROM coordinator_decision_inputs
            WHERE coordinator_decision_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (coordinator_decision_id,),
        ).fetchall()

    def list_conflicts_for_decision(self, conn: Connection, coordinator_decision_id: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT coordinator_decision_id, conflict_type, conflict_key, conflict_reason,
                   conflict_severity, left_brain, right_brain, left_output_id, right_output_id, created_at
            FROM coordinator_decision_conflicts
            WHERE coordinator_decision_id = %s
            ORDER BY conflict_severity DESC NULLS LAST, created_at DESC, id DESC
            """,
            (coordinator_decision_id,),
        ).fetchall()

    def list_recent_decisions(
        self,
        conn: Connection,
        *,
        limit: int = 50,
        market_id: str | None = None,
        position_id: str | None = None,
        final_state: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        filters: list[str] = []
        params: list[Any] = []
        if market_id:
            filters.append("market_id = %s")
            params.append(market_id)
        if position_id:
            filters.append("position_id = %s")
            params.append(position_id)
        if final_state:
            filters.append("final_state = %s")
            params.append(final_state.strip().upper())
        if status:
            filters.append("status = %s")
            params.append(status.strip().upper())
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM coordinator_decisions
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()

    def list_decisions_by_market(self, conn: Connection, market_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_decisions(conn, market_id=market_id, limit=limit)

    def list_decisions_by_position(self, conn: Connection, position_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_recent_decisions(conn, position_id=position_id, limit=limit)

    def list_conflicts(self, conn: Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT coordinator_decision_id, conflict_type, conflict_key, conflict_reason,
                   conflict_severity, left_brain, right_brain, left_output_id, right_output_id, created_at
            FROM coordinator_decision_conflicts
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

    def list_brain_outputs_by_ids(self, conn: Connection, brain_output_ids: list[str]) -> list[dict[str, Any]]:
        if not brain_output_ids:
            return []
        return conn.execute(
            """
            SELECT *
            FROM brain_outputs
            WHERE brain_output_id = ANY(%s)
            ORDER BY created_at DESC, id DESC
            """,
            (brain_output_ids,),
        ).fetchall()

    def list_brain_outputs_for_market(self, conn: Connection, market_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM brain_outputs
            WHERE market_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (market_id, limit),
        ).fetchall()

    def list_brain_outputs_for_position(self, conn: Connection, position_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT *
            FROM brain_outputs
            WHERE position_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (position_id, limit),
        ).fetchall()

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS total_decisions_24h,
                COUNT(*) FILTER (WHERE conflicts_detected IS TRUE AND created_at >= now() - interval '24 hours') AS conflicts_detected_24h,
                COUNT(*) FILTER (WHERE final_state = 'NO_TRADE' AND created_at >= now() - interval '24 hours') AS no_trade_decisions_24h,
                COUNT(*) FILTER (WHERE final_state = 'RISK_BLOCKED' AND created_at >= now() - interval '24 hours') AS risk_blocked_24h,
                COUNT(*) FILTER (WHERE final_state = 'REVIEW_REQUIRED' AND created_at >= now() - interval '24 hours') AS review_required_24h,
                COUNT(*) FILTER (WHERE execution_allowed IS TRUE) AS execution_allowed_count,
                COUNT(*) FILTER (WHERE governor_required IS TRUE AND created_at >= now() - interval '24 hours') AS decisions_requiring_governor
            FROM coordinator_decisions
            """
        ).fetchone()
        by_state = conn.execute(
            """
            SELECT final_state, COUNT(*) AS count
            FROM coordinator_decisions
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY final_state
            ORDER BY count DESC, final_state ASC
            """
        ).fetchall()
        blocked_actions = conn.execute(
            """
            SELECT action, COUNT(*) AS count
            FROM coordinator_decisions, jsonb_array_elements_text(blocked_actions_json) AS action
            WHERE created_at >= now() - interval '24 hours'
            GROUP BY action
            ORDER BY count DESC, action ASC
            """
        ).fetchall()
        return {
            "total_decisions_24h": int(totals["total_decisions_24h"] or 0),
            "decisions_by_state": [dict(row) for row in by_state],
            "recent_decisions": [dict(row) for row in self.list_recent_decisions(conn, limit=limit)],
            "recent_conflicts": [dict(row) for row in self.list_conflicts(conn, limit=limit)],
            "conflicts_detected_24h": int(totals["conflicts_detected_24h"] or 0),
            "no_trade_decisions_24h": int(totals["no_trade_decisions_24h"] or 0),
            "risk_blocked_24h": int(totals["risk_blocked_24h"] or 0),
            "review_required_24h": int(totals["review_required_24h"] or 0),
            "execution_allowed_count": int(totals["execution_allowed_count"] or 0),
            "decisions_requiring_governor": int(totals["decisions_requiring_governor"] or 0),
            "blocked_actions_summary": [dict(row) for row in blocked_actions],
        }


def _decision_params(decision: CoordinatorDecision) -> dict[str, Any]:
    data = decision.model_dump()
    data["approved_actions_json"] = Jsonb(json.loads(json.dumps(data.pop("approved_actions", []) or [], default=str)))
    data["blocked_actions_json"] = Jsonb(json.loads(json.dumps(data.pop("blocked_actions", []) or [], default=str)))
    data["required_reviews_json"] = Jsonb(json.loads(json.dumps(data.pop("required_reviews", []) or [], default=str)))
    data["risk_flags_json"] = Jsonb(json.loads(json.dumps(data.pop("risk_flags", []) or [], default=str)))
    data["metadata_json"] = Jsonb(json.loads(json.dumps(data.pop("metadata", {}) or {}, default=str)))
    return data
