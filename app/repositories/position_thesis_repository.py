from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.neural_mesh.position_thesis import PositionThesisProfile, ThesisValidationResult


class PositionThesisRepository:
    def create_profile(self, conn: Connection, profile: PositionThesisProfile) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_thesis_profiles (
                thesis_id, position_id, market_id, side, entry_thesis, profit_drivers_json,
                invalidation_drivers_json, watch_entities_json, danger_signals_json,
                take_profit_rules_json, partial_exit_rules_json, emergency_exit_rules_json,
                status, completeness_score, paper_ready, live_ready, coordinator_decision_id,
                brain_output_id, source_signal_ids_json, risk_flags_json, thesis_version,
                created_by, reviewed_by, reviewed_at, expires_at, metadata_json, created_at, updated_at
            )
            VALUES (
                %(thesis_id)s, %(position_id)s, %(market_id)s, %(side)s, %(entry_thesis)s,
                %(profit_drivers_json)s, %(invalidation_drivers_json)s, %(watch_entities_json)s,
                %(danger_signals_json)s, %(take_profit_rules_json)s, %(partial_exit_rules_json)s,
                %(emergency_exit_rules_json)s, %(status)s, %(completeness_score)s, %(paper_ready)s,
                %(live_ready)s, %(coordinator_decision_id)s, %(brain_output_id)s,
                %(source_signal_ids_json)s, %(risk_flags_json)s, %(thesis_version)s,
                %(created_by)s, %(reviewed_by)s, %(reviewed_at)s, %(expires_at)s,
                %(metadata_json)s, COALESCE(%(created_at)s, now()), COALESCE(%(updated_at)s, now())
            )
            RETURNING *
            """,
            _profile_params(profile),
        ).fetchone()
        return dict(row)

    def update_profile(self, conn: Connection, profile: PositionThesisProfile) -> dict[str, Any]:
        row = conn.execute(
            """
            UPDATE position_thesis_profiles
            SET
                position_id = %(position_id)s,
                market_id = %(market_id)s,
                side = %(side)s,
                entry_thesis = %(entry_thesis)s,
                profit_drivers_json = %(profit_drivers_json)s,
                invalidation_drivers_json = %(invalidation_drivers_json)s,
                watch_entities_json = %(watch_entities_json)s,
                danger_signals_json = %(danger_signals_json)s,
                take_profit_rules_json = %(take_profit_rules_json)s,
                partial_exit_rules_json = %(partial_exit_rules_json)s,
                emergency_exit_rules_json = %(emergency_exit_rules_json)s,
                status = %(status)s,
                completeness_score = %(completeness_score)s,
                paper_ready = %(paper_ready)s,
                live_ready = %(live_ready)s,
                coordinator_decision_id = %(coordinator_decision_id)s,
                brain_output_id = %(brain_output_id)s,
                source_signal_ids_json = %(source_signal_ids_json)s,
                risk_flags_json = %(risk_flags_json)s,
                thesis_version = %(thesis_version)s,
                created_by = %(created_by)s,
                reviewed_by = %(reviewed_by)s,
                reviewed_at = %(reviewed_at)s,
                expires_at = %(expires_at)s,
                metadata_json = %(metadata_json)s,
                updated_at = now()
            WHERE thesis_id = %(thesis_id)s
            RETURNING *
            """,
            _profile_params(profile),
        ).fetchone()
        if row is None:
            raise ValueError(f"thesis profile not found: {profile.thesis_id}")
        return dict(row)

    def get_by_id(self, conn: Connection, thesis_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM position_thesis_profiles WHERE thesis_id = %s",
            (thesis_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_position(self, conn: Connection, position_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM position_thesis_profiles
            WHERE position_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_profiles(
        self,
        conn: Connection,
        *,
        status: str | None = None,
        market_id: str | None = None,
        position_id: str | None = None,
        paper_ready: bool | None = None,
        live_ready: bool | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status.upper())
        if market_id:
            clauses.append("market_id = %s")
            params.append(market_id)
        if position_id:
            clauses.append("position_id = %s")
            params.append(position_id)
        if paper_ready is not None:
            clauses.append("paper_ready = %s")
            params.append(paper_ready)
        if live_ready is not None:
            clauses.append("live_ready = %s")
            params.append(live_ready)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        return conn.execute(
            f"""
            SELECT *
            FROM position_thesis_profiles
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        ).fetchall()

    def record_validation_event(
        self,
        conn: Connection,
        *,
        thesis_id: str,
        validation: ThesisValidationResult,
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_thesis_validation_events (
                thesis_id, validation_status, completeness_score, paper_ready, live_ready,
                missing_fields_json, validation_errors_json, created_at
            )
            VALUES (
                %(thesis_id)s, %(validation_status)s, %(completeness_score)s,
                %(paper_ready)s, %(live_ready)s, %(missing_fields_json)s,
                %(validation_errors_json)s, now()
            )
            RETURNING *
            """,
            {
                "thesis_id": thesis_id,
                "validation_status": validation.validation_status,
                "completeness_score": validation.completeness_score,
                "paper_ready": validation.paper_ready,
                "live_ready": validation.live_ready,
                "missing_fields_json": Jsonb(validation.missing_fields),
                "validation_errors_json": Jsonb(validation.validation_errors),
            },
        ).fetchone()
        return dict(row)

    def summary(self, conn: Connection, *, limit: int = 10) -> dict[str, Any]:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) AS total_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'DRAFT') AS draft_thesis_profiles,
                COUNT(*) FILTER (WHERE status = 'NEEDS_REVIEW') AS needs_review,
                COUNT(*) FILTER (WHERE status = 'INVALIDATED') AS invalidated,
                COUNT(*) FILTER (WHERE paper_ready = true) AS paper_ready,
                COUNT(*) FILTER (WHERE live_ready = true) AS live_ready,
                COALESCE(AVG(completeness_score), 0) AS avg_completeness_score,
                MAX(updated_at) AS latest_at
            FROM position_thesis_profiles
            """
        ).fetchone()
        latest = conn.execute(
            """
            SELECT *
            FROM position_thesis_profiles
            ORDER BY created_at DESC, id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        missing = conn.execute(
            """
            SELECT field, COUNT(*) AS count
            FROM position_thesis_validation_events,
                 jsonb_array_elements_text(missing_fields_json) AS field
            GROUP BY field
            ORDER BY count DESC, field ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        positions_without_thesis = self.positions_without_thesis_count(conn)
        return {
            **dict(totals),
            "positions_without_thesis": positions_without_thesis,
            "latest_thesis_profiles": [dict(row) for row in latest],
            "missing_required_fields_summary": [dict(row) for row in missing],
        }

    def positions_without_thesis_count(self, conn: Connection) -> int:
        row = conn.execute(
            """
            WITH candidate_positions AS (
                SELECT id::text AS position_id FROM positions
                UNION
                SELECT id::text AS position_id FROM paper_positions
                UNION
                SELECT id::text AS position_id FROM shadow_positions
            )
            SELECT COUNT(*) AS count
            FROM candidate_positions p
            WHERE NOT EXISTS (
                SELECT 1
                FROM position_thesis_profiles t
                WHERE t.position_id = p.position_id
            )
            """
        ).fetchone()
        return int(row["count"] or 0)


def _profile_params(profile: PositionThesisProfile) -> dict[str, Any]:
    data = profile.model_dump()
    for field in (
        "profit_drivers",
        "invalidation_drivers",
        "watch_entities",
        "danger_signals",
        "take_profit_rules",
        "partial_exit_rules",
        "emergency_exit_rules",
        "source_signal_ids",
        "risk_flags",
    ):
        data[f"{field}_json"] = Jsonb(json.loads(json.dumps(data.pop(field, []) or [], default=str)))
    data["metadata_json"] = Jsonb(json.loads(json.dumps(data.pop("metadata", {}) or {}, default=str)))
    return data
