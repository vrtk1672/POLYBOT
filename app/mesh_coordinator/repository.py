from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class MeshCoordinatorRepository:
    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_bundle(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_input_bundles
            WHERE session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_bundles(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_coordinator_input_bundles
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def list_opinions(self, conn: Connection, session_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_brain_opinions
                WHERE session_id = %s
                  AND brain_type <> 'COORDINATOR_OBSERVER'
                ORDER BY created_at DESC, id DESC
                """,
                (session_id,),
            ).fetchall()
        ]

    def upsert_decision(self, conn: Connection, decision: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_coordinator_decisions (
                decision_id, session_id, bundle_id, market_id, candidate_id, position_id,
                final_stance, final_action, confidence, source_brain_count, opinion_count,
                conflicts_detected, conflict_count, winning_brains_json, losing_brains_json,
                supporting_opinions_json, opposing_opinions_json, decision_reason,
                safety_status, coordinator_ready, created_at
            )
            VALUES (
                %(decision_id)s, %(session_id)s, %(bundle_id)s, %(market_id)s,
                %(candidate_id)s, %(position_id)s, %(final_stance)s, %(final_action)s,
                %(confidence)s, %(source_brain_count)s, %(opinion_count)s,
                %(conflicts_detected)s, %(conflict_count)s, %(winning_brains_json)s,
                %(losing_brains_json)s, %(supporting_opinions_json)s,
                %(opposing_opinions_json)s, %(decision_reason)s, %(safety_status)s,
                %(coordinator_ready)s, now()
            )
            ON CONFLICT (session_id, bundle_id) DO UPDATE
            SET market_id = EXCLUDED.market_id,
                candidate_id = EXCLUDED.candidate_id,
                position_id = EXCLUDED.position_id,
                final_stance = EXCLUDED.final_stance,
                final_action = EXCLUDED.final_action,
                confidence = EXCLUDED.confidence,
                source_brain_count = EXCLUDED.source_brain_count,
                opinion_count = EXCLUDED.opinion_count,
                conflicts_detected = EXCLUDED.conflicts_detected,
                conflict_count = EXCLUDED.conflict_count,
                winning_brains_json = EXCLUDED.winning_brains_json,
                losing_brains_json = EXCLUDED.losing_brains_json,
                supporting_opinions_json = EXCLUDED.supporting_opinions_json,
                opposing_opinions_json = EXCLUDED.opposing_opinions_json,
                decision_reason = EXCLUDED.decision_reason,
                safety_status = EXCLUDED.safety_status,
                coordinator_ready = EXCLUDED.coordinator_ready,
                created_at = now()
            RETURNING *
            """,
            {
                **decision,
                "winning_brains_json": Jsonb(decision["winning_brains_json"]),
                "losing_brains_json": Jsonb(decision["losing_brains_json"]),
                "supporting_opinions_json": Jsonb(decision["supporting_opinions_json"]),
                "opposing_opinions_json": Jsonb(decision["opposing_opinions_json"]),
            },
        ).fetchone()
        assert row is not None
        return dict(row)

    def replace_sources(self, conn: Connection, *, decision_id: str, sources: list[dict[str, Any]]) -> None:
        conn.execute("DELETE FROM mesh_coordinator_decision_sources WHERE decision_id = %s", (decision_id,))
        for source in sources:
            conn.execute(
                """
                INSERT INTO mesh_coordinator_decision_sources (
                    decision_id, opinion_id, brain_name, brain_type, stance,
                    confidence, influence, contribution_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (decision_id, opinion_id) DO NOTHING
                """,
                (
                    decision_id,
                    source["opinion_id"],
                    source["brain_name"],
                    source["brain_type"],
                    source["stance"],
                    source["confidence"],
                    source["influence"],
                    source["contribution_summary"],
                ),
            )

    def replace_conflicts(self, conn: Connection, *, decision_id: str, conflicts: list[dict[str, Any]]) -> None:
        conn.execute("DELETE FROM mesh_conflict_records WHERE decision_id = %s", (decision_id,))
        for conflict in conflicts:
            conn.execute(
                """
                INSERT INTO mesh_conflict_records (
                    conflict_id, session_id, bundle_id, decision_id, conflict_type,
                    brain_a, stance_a, brain_b, stance_b, severity, resolution,
                    winner, reason
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (conflict_id) DO NOTHING
                """,
                (
                    conflict["conflict_id"],
                    conflict["session_id"],
                    conflict["bundle_id"],
                    decision_id,
                    conflict["conflict_type"],
                    conflict["brain_a"],
                    conflict["stance_a"],
                    conflict["brain_b"],
                    conflict["stance_b"],
                    conflict["severity"],
                    conflict["resolution"],
                    conflict.get("winner"),
                    conflict["reason"],
                ),
            )

    def dashboard_rows(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT d.*, s.session_type, s.title
                FROM mesh_coordinator_decisions d
                LEFT JOIN mesh_sessions s ON s.session_id = d.session_id
                ORDER BY d.created_at DESC, d.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def get_decision(self, conn: Connection, decision_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_coordinator_decisions WHERE decision_id = %s", (decision_id,)).fetchone()
        return dict(row) if row else None

    def latest_decision_for_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_decisions
            WHERE session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def detail(self, conn: Connection, decision_id: str) -> dict[str, Any] | None:
        decision = self.get_decision(conn, decision_id)
        if not decision:
            return None
        session = self.get_session(conn, str(decision["session_id"]))
        bundle = conn.execute("SELECT * FROM mesh_coordinator_input_bundles WHERE bundle_id = %s", (decision["bundle_id"],)).fetchone()
        opinions = self.list_opinions(conn, str(decision["session_id"]))
        sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_coordinator_decision_sources
                WHERE decision_id = %s
                ORDER BY linked_at DESC, id DESC
                """,
                (decision_id,),
            ).fetchall()
        ]
        conflicts = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_conflict_records
                WHERE decision_id = %s
                ORDER BY severity DESC, created_at DESC, id DESC
                """,
                (decision_id,),
            ).fetchall()
        ]
        return {
            "decision": decision,
            "source_bundle": dict(bundle) if bundle else None,
            "source_opinions": opinions,
            "conflicts": conflicts,
            "winning_brains": decision.get("winning_brains_json") or [],
            "losing_brains": decision.get("losing_brains_json") or [],
            "source_refs": sources,
            "session": session,
        }


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None
