from __future__ import annotations

import hashlib
from typing import Any

from psycopg import Connection


class PositionAwarenessRepository:
    def get_position(self, conn: Connection, position_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "paper_positions"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM paper_positions
            WHERE id::text = %s OR payload_json->>'paper_position_id' = %s
            ORDER BY updated_at DESC NULLS LAST, opened_at DESC NULLS LAST
            LIMIT 1
            """,
            (position_id, position_id),
        ).fetchone()
        return dict(row) if row else None

    def list_active_positions(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        if not table_exists(conn, "paper_positions"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM paper_positions
                WHERE current_status IN ('OPEN', 'EXIT_PENDING')
                  AND closed_at IS NULL
                  AND COALESCE(excluded_from_active_paper_truth, false) = false
                ORDER BY updated_at DESC NULLS LAST, opened_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_position_session(self, conn: Connection, position_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "mesh_sessions"):
            return None
        row = conn.execute(
            """
            SELECT *
            FROM mesh_sessions
            WHERE session_type = 'POSITION_SESSION'
              AND position_id = %s
            ORDER BY opened_at DESC, id DESC
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()
        return dict(row) if row else None

    def ensure_position_session(self, conn: Connection, position: dict[str, Any]) -> dict[str, Any]:
        position_id = str(position["id"])
        session_id = _position_session_id(position_id)
        row = conn.execute(
            """
            INSERT INTO mesh_sessions (
                session_id, session_type, market_id, position_id, title,
                status, priority, opened_at, last_event_at, event_count,
                participant_count, metadata_json
            )
            VALUES (
                %s, 'POSITION_SESSION', %s, %s, %s,
                'OPEN', 2, COALESCE(%s, now()), COALESCE(%s, now()), 0,
                1, jsonb_build_object(
                    'identity_key', %s::text,
                    'created_from_table', 'paper_positions',
                    'created_from_record_id', %s::text
                )
            )
            ON CONFLICT (session_id) DO UPDATE
            SET market_id = EXCLUDED.market_id,
                position_id = EXCLUDED.position_id,
                title = EXCLUDED.title,
                last_event_at = GREATEST(mesh_sessions.last_event_at, EXCLUDED.last_event_at),
                participant_count = GREATEST(mesh_sessions.participant_count, 1)
            RETURNING *
            """,
            (
                session_id,
                position.get("market_id"),
                position_id,
                f"POSITION_SESSION {position_id}",
                position.get("opened_at"),
                position.get("updated_at") or position.get("opened_at"),
                position_id,
                position_id,
            ),
        ).fetchone()
        assert row is not None
        conn.execute(
            """
            INSERT INTO mesh_session_participants (
                session_id, component, component_type, metadata_json
            )
            VALUES (%s, 'Position Awareness', 'position_awareness', jsonb_build_object('source_table', 'paper_positions'))
            ON CONFLICT (session_id, component) DO UPDATE
            SET last_seen_at = now(),
                message_count = mesh_session_participants.message_count + 1
            """,
            (session_id,),
        )
        return dict(row)

    def linked_events(self, conn: Connection, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        if not table_exists(conn, "mesh_session_events") or not table_exists(conn, "neural_events"):
            return []
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.*
                FROM mesh_session_events se
                JOIN neural_events e ON e.event_id = se.event_id
                WHERE se.session_id = %s
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]

    def shared_awareness(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "mesh_shared_awareness"):
            return None
        row = conn.execute(
            "SELECT * FROM mesh_shared_awareness WHERE session_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

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

    def latest_coordinator_decision(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        if not table_exists(conn, "mesh_coordinator_decisions"):
            return None
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

    def upsert_awareness(
        self,
        conn: Connection,
        awareness: dict[str, Any],
        *,
        reactions: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO position_awareness (
                awareness_id, position_id, session_id, market_id, side,
                entry_price, current_price, pnl, pnl_pct, exposure,
                age_minutes, liquidity_status, risk_status, exit_status,
                capital_status, coordinator_status, awareness_score, updated_at
            )
            VALUES (
                %(awareness_id)s, %(position_id)s, %(session_id)s, %(market_id)s,
                %(side)s, %(entry_price)s, %(current_price)s, %(pnl)s,
                %(pnl_pct)s, %(exposure)s, %(age_minutes)s, %(liquidity_status)s,
                %(risk_status)s, %(exit_status)s, %(capital_status)s,
                %(coordinator_status)s, %(awareness_score)s, now()
            )
            ON CONFLICT (position_id) DO UPDATE
            SET session_id = EXCLUDED.session_id,
                market_id = EXCLUDED.market_id,
                side = EXCLUDED.side,
                entry_price = EXCLUDED.entry_price,
                current_price = EXCLUDED.current_price,
                pnl = EXCLUDED.pnl,
                pnl_pct = EXCLUDED.pnl_pct,
                exposure = EXCLUDED.exposure,
                age_minutes = EXCLUDED.age_minutes,
                liquidity_status = EXCLUDED.liquidity_status,
                risk_status = EXCLUDED.risk_status,
                exit_status = EXCLUDED.exit_status,
                capital_status = EXCLUDED.capital_status,
                coordinator_status = EXCLUDED.coordinator_status,
                awareness_score = EXCLUDED.awareness_score,
                updated_at = now()
            RETURNING *
            """,
            awareness,
        ).fetchone()
        assert row is not None
        for reaction in reactions:
            conn.execute(
                """
                INSERT INTO position_reactions (
                    reaction_id, position_id, session_id, reaction_type,
                    source_event_id, source_domain, source_component,
                    severity, summary
                )
                VALUES (
                    %(reaction_id)s, %(position_id)s, %(session_id)s,
                    %(reaction_type)s, %(source_event_id)s, %(source_domain)s,
                    %(source_component)s, %(severity)s, %(summary)s
                )
                ON CONFLICT (reaction_id) DO UPDATE
                SET severity = EXCLUDED.severity,
                    summary = EXCLUDED.summary
                """,
                reaction,
            )
        for source in sources:
            conn.execute(
                """
                INSERT INTO position_context_sources (
                    position_id, session_id, source_table, source_record_id,
                    source_domain, contribution_summary
                )
                VALUES (
                    %(position_id)s, %(session_id)s, %(source_table)s,
                    %(source_record_id)s, %(source_domain)s,
                    %(contribution_summary)s
                )
                ON CONFLICT (position_id, session_id, source_table, source_record_id, source_domain) DO UPDATE
                SET contribution_summary = EXCLUDED.contribution_summary,
                    linked_at = now()
                """,
                source,
            )
        return dict(row)

    def dashboard_rows(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT pa.*, s.session_type, s.status AS session_status, s.title
                FROM position_awareness pa
                LEFT JOIN mesh_sessions s ON s.session_id = pa.session_id
                ORDER BY pa.updated_at DESC, pa.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def detail(self, conn: Connection, position_id: str, *, limit: int = 100) -> dict[str, Any] | None:
        awareness = conn.execute(
            """
            SELECT *
            FROM position_awareness
            WHERE position_id = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (position_id,),
        ).fetchone()
        if not awareness:
            return None
        awareness_dict = dict(awareness)
        session_id = str(awareness_dict["session_id"])
        reactions = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM position_reactions
                WHERE position_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (position_id, limit),
            ).fetchall()
        ]
        sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM position_context_sources
                WHERE position_id = %s
                ORDER BY linked_at DESC, id DESC
                LIMIT %s
                """,
                (position_id, limit),
            ).fetchall()
        ]
        coordinator = self.latest_coordinator_decision(conn, session_id)
        session = self.get_session(conn, session_id)
        return {
            "awareness": awareness_dict,
            "reactions": reactions,
            "sources": sources,
            "related_session": session,
            "coordinator_visibility": coordinator,
            "risk_status": awareness_dict.get("risk_status"),
            "exit_status": awareness_dict.get("exit_status"),
            "capital_status": awareness_dict.get("capital_status"),
        }


def position_session_id(position_id: str) -> str:
    return _position_session_id(position_id)


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None


def _position_session_id(position_id: str) -> str:
    digest = hashlib.sha256(f"POSITION_SESSION:{position_id}".encode("utf-8")).hexdigest()[:24]
    return f"mesh_session_position_session_{digest}"
