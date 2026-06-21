from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class MultiBrainConsumptionRepository:
    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_awareness(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_shared_awareness WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def awareness_sources(self, conn: Connection, awareness_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_awareness_sources
                WHERE awareness_id = %s
                ORDER BY source_domain, source_created_at DESC NULLS LAST, id DESC
                """,
                (awareness_id,),
            ).fetchall()
        ]

    def latest_capital_evaluation(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "capital_brain_evaluations"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM capital_brain_evaluations
            WHERE session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def latest_position_awareness(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "position_awareness"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM position_awareness
            WHERE session_id = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_awareness_sessions(self, conn: Connection, *, limit: int = 100) -> list[str]:
        return [
            str(row["session_id"])
            for row in conn.execute(
                """
                SELECT session_id
                FROM mesh_shared_awareness
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def upsert_opinion(self, conn: Connection, opinion: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_brain_opinions (
                opinion_id, session_id, brain_name, brain_type, market_id, candidate_id, position_id,
                stance, confidence, decision_bias, reasoning_summary, consumed_domains_json,
                missing_domains_json, stale_domains_json, supporting_sources_json,
                opposing_sources_json, conflicts_json, created_at
            )
            VALUES (
                %(opinion_id)s, %(session_id)s, %(brain_name)s, %(brain_type)s,
                %(market_id)s, %(candidate_id)s, %(position_id)s, %(stance)s,
                %(confidence)s, %(decision_bias)s, %(reasoning_summary)s,
                %(consumed_domains_json)s, %(missing_domains_json)s, %(stale_domains_json)s,
                %(supporting_sources_json)s, %(opposing_sources_json)s, %(conflicts_json)s, now()
            )
            ON CONFLICT (session_id, brain_type) DO UPDATE
            SET brain_name = EXCLUDED.brain_name,
                market_id = EXCLUDED.market_id,
                candidate_id = EXCLUDED.candidate_id,
                position_id = EXCLUDED.position_id,
                stance = EXCLUDED.stance,
                confidence = EXCLUDED.confidence,
                decision_bias = EXCLUDED.decision_bias,
                reasoning_summary = EXCLUDED.reasoning_summary,
                consumed_domains_json = EXCLUDED.consumed_domains_json,
                missing_domains_json = EXCLUDED.missing_domains_json,
                stale_domains_json = EXCLUDED.stale_domains_json,
                supporting_sources_json = EXCLUDED.supporting_sources_json,
                opposing_sources_json = EXCLUDED.opposing_sources_json,
                conflicts_json = EXCLUDED.conflicts_json,
                created_at = now()
            RETURNING *
            """,
            {
                **opinion,
                "consumed_domains_json": Jsonb(opinion["consumed_domains_json"]),
                "missing_domains_json": Jsonb(opinion["missing_domains_json"]),
                "stale_domains_json": Jsonb(opinion["stale_domains_json"]),
                "supporting_sources_json": Jsonb(opinion["supporting_sources_json"]),
                "opposing_sources_json": Jsonb(opinion["opposing_sources_json"]),
                "conflicts_json": Jsonb(opinion["conflicts_json"]),
            },
        ).fetchone()
        assert row is not None
        return dict(row)

    def replace_sources(self, conn: Connection, *, opinion_id: str, session_id: str, sources: list[dict[str, Any]]) -> None:
        conn.execute("DELETE FROM mesh_brain_consumption_sources WHERE opinion_id = %s", (opinion_id,))
        for source in sources:
            conn.execute(
                """
                INSERT INTO mesh_brain_consumption_sources (
                    opinion_id, session_id, source_domain, source_table, source_record_id,
                    source_status, influence, contribution_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (opinion_id, source_domain, source_table, source_record_id) DO NOTHING
                """,
                (
                    opinion_id,
                    session_id,
                    source["source_domain"],
                    source["source_table"],
                    source["source_record_id"],
                    source["source_status"],
                    source["influence"],
                    source["contribution_summary"],
                ),
            )

    def delete_position_opinion_if_not_applicable(self, conn: Connection, session_id: str) -> None:
        row = conn.execute(
            """
            SELECT opinion_id
            FROM mesh_brain_opinions
            WHERE session_id = %s AND brain_type = 'POSITION_BRAIN'
            """,
            (session_id,),
        ).fetchone()
        if row:
            conn.execute("DELETE FROM mesh_brain_opinions WHERE opinion_id = %s", (row["opinion_id"],))

    def opinions_for_session(self, conn: Connection, session_id: str) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_brain_opinions
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                """,
                (session_id,),
            ).fetchall()
        ]

    def upsert_bundle(self, conn: Connection, bundle: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_coordinator_input_bundles (
                bundle_id, session_id, market_id, candidate_id, position_id,
                source_brain_count, opinion_count, stance_summary_json,
                conflicts_detected, conflict_count, coordinator_ready, created_at
            )
            VALUES (
                %(bundle_id)s, %(session_id)s, %(market_id)s, %(candidate_id)s, %(position_id)s,
                %(source_brain_count)s, %(opinion_count)s, %(stance_summary_json)s,
                %(conflicts_detected)s, %(conflict_count)s, %(coordinator_ready)s, now()
            )
            ON CONFLICT (session_id) DO UPDATE
            SET market_id = EXCLUDED.market_id,
                candidate_id = EXCLUDED.candidate_id,
                position_id = EXCLUDED.position_id,
                source_brain_count = EXCLUDED.source_brain_count,
                opinion_count = EXCLUDED.opinion_count,
                stance_summary_json = EXCLUDED.stance_summary_json,
                conflicts_detected = EXCLUDED.conflicts_detected,
                conflict_count = EXCLUDED.conflict_count,
                coordinator_ready = EXCLUDED.coordinator_ready,
                created_at = now()
            RETURNING *
            """,
            {**bundle, "stance_summary_json": Jsonb(bundle["stance_summary_json"])},
        ).fetchone()
        assert row is not None
        return dict(row)

    def dashboard_rows(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT b.*, s.session_type, s.title
                FROM mesh_coordinator_input_bundles b
                LEFT JOIN mesh_sessions s ON s.session_id = b.session_id
                ORDER BY b.created_at DESC, b.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def detail(self, conn: Connection, session_id: str, *, limit: int = 100) -> dict[str, Any] | None:
        session = self.get_session(conn, session_id)
        awareness = self.get_awareness(conn, session_id)
        if not session:
            return None
        opinions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_brain_opinions
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]
        sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_brain_consumption_sources
                WHERE session_id = %s
                ORDER BY linked_at DESC, id DESC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]
        bundle = conn.execute(
            """
            SELECT *
            FROM mesh_coordinator_input_bundles
            WHERE session_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        dialogue = []
        if table_exists(conn, "brain_dialogue_events"):
            dialogue = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM brain_dialogue_events
                    WHERE source_table IN ('mesh_brain_opinions', 'mesh_coordinator_input_bundles')
                      AND (raw_payload_json->>'session_id' = %s OR source_record_id LIKE %s)
                    ORDER BY timestamp DESC, id DESC
                    LIMIT %s
                    """,
                    (session_id, f"%{session_id}%", limit),
                ).fetchall()
            ]
        return {
            "session": session,
            "shared_awareness": awareness,
            "brain_opinions": opinions,
            "consumed_sources": sources,
            "coordinator_input_bundle": dict(bundle) if bundle else None,
            "conflicts": (bundle or {}).get("stance_summary_json", {}).get("conflicts", []) if bundle else [],
            "dialogue_messages": dialogue,
        }


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None
