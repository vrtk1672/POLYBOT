from __future__ import annotations

from datetime import timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class MeshSessionRepository:
    def upsert_session(self, conn: Connection, *, spec: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO mesh_sessions (
                session_id, session_type, market_id, candidate_id, position_id, correlation_id,
                title, status, priority, opened_at, last_event_at, event_count,
                participant_count, threat_context, opportunity_context, metadata_json
            )
            VALUES (
                %(session_id)s, %(session_type)s, %(market_id)s, %(candidate_id)s, %(position_id)s, %(correlation_id)s,
                %(title)s, 'OPEN', %(priority)s, %(created_at)s, %(created_at)s, 0,
                0, %(threat_context)s, %(opportunity_context)s, %(metadata_json)s
            )
            ON CONFLICT (session_id) DO UPDATE
            SET last_event_at = GREATEST(mesh_sessions.last_event_at, EXCLUDED.last_event_at),
                priority = LEAST(mesh_sessions.priority, EXCLUDED.priority),
                threat_context = mesh_sessions.threat_context OR EXCLUDED.threat_context,
                opportunity_context = mesh_sessions.opportunity_context OR EXCLUDED.opportunity_context,
                metadata_json = mesh_sessions.metadata_json || EXCLUDED.metadata_json
            RETURNING *
            """,
            {
                **spec,
                "priority": int(event.get("priority") or 5),
                "created_at": event.get("created_at"),
                "metadata_json": Jsonb(spec.get("metadata_json") or {}),
            },
        ).fetchone()
        assert row is not None
        return dict(row)

    def link_event(self, conn: Connection, *, session_id: str, event: dict[str, Any], role: str, metadata: dict[str, Any] | None = None) -> bool:
        result = conn.execute(
            """
            INSERT INTO mesh_session_events (
                session_id, event_id, event_type, source_component, role, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_id, event_id) DO NOTHING
            """,
            (
                session_id,
                event["event_id"],
                event["event_type"],
                event["source_component"],
                role,
                Jsonb(metadata or {}),
            ),
        )
        return bool(result.rowcount)

    def upsert_participant(self, conn: Connection, *, session_id: str, component: str, component_type: str, metadata: dict[str, Any] | None = None) -> None:
        conn.execute(
            """
            INSERT INTO mesh_session_participants (
                session_id, component, component_type, message_count, metadata_json
            )
            VALUES (%s, %s, %s, 1, %s)
            ON CONFLICT (session_id, component) DO UPDATE
            SET last_seen_at = now(),
                message_count = mesh_session_participants.message_count + 1,
                metadata_json = mesh_session_participants.metadata_json || EXCLUDED.metadata_json
            """,
            (session_id, component, component_type, Jsonb(metadata or {})),
        )

    def recompute_session_counts(self, conn: Connection, session_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            WITH event_counts AS (
                SELECT session_id, COUNT(*) AS event_count, MAX(linked_at) AS last_event_at
                FROM mesh_session_events
                WHERE session_id = %s
                GROUP BY session_id
            ),
            participant_counts AS (
                SELECT session_id, COUNT(*) AS participant_count
                FROM mesh_session_participants
                WHERE session_id = %s
                GROUP BY session_id
            )
            UPDATE mesh_sessions s
            SET event_count = COALESCE(e.event_count, 0),
                participant_count = COALESCE(p.participant_count, 0),
                last_event_at = COALESCE(e.last_event_at, s.last_event_at),
                status = CASE
                    WHEN s.closed_at IS NOT NULL THEN 'CLOSED'
                    WHEN COALESCE(e.event_count, 0) > 1 OR COALESCE(p.participant_count, 0) > 1 THEN 'ACTIVE'
                    ELSE s.status
                END
            FROM event_counts e
            FULL OUTER JOIN participant_counts p ON p.session_id = e.session_id
            WHERE s.session_id = %s
            RETURNING s.*
            """,
            (session_id, session_id, session_id),
        ).fetchone()
        if row is not None:
            return dict(row)
        return self.get_session(conn, session_id) or {}

    def mark_closed_if_needed(self, conn: Connection, *, session_id: str, event: dict[str, Any]) -> None:
        payload = event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {}
        event_type = str(event.get("event_type") or "")
        should_close = event_type == "POSITION_CLOSED" or payload.get("closed_at") or payload.get("market_status") == "CLOSED"
        if not should_close:
            return
        conn.execute(
            """
            UPDATE mesh_sessions
            SET status = 'CLOSED',
                closed_at = COALESCE(closed_at, now())
            WHERE session_id = %s
            """,
            (session_id,),
        )

    def mark_stale_sessions(self, conn: Connection, *, stale_after: timedelta) -> int:
        result = conn.execute(
            """
            UPDATE mesh_sessions
            SET status = 'STALE'
            WHERE status IN ('OPEN', 'ACTIVE')
              AND last_event_at < now() - (%s::text || ' seconds')::interval
            """,
            (int(stale_after.total_seconds()),),
        )
        return int(result.rowcount or 0)

    def upsert_state(self, conn: Connection, *, session_id: str, updates: dict[str, Any]) -> None:
        fields = {
            "latest_market_state_json": {},
            "latest_candidate_state_json": {},
            "latest_position_state_json": {},
            "latest_risk_state_json": {},
            "latest_exit_state_json": {},
            "latest_capital_state_json": {},
            "latest_news_state_json": {},
            "latest_liquidity_state_json": {},
            "latest_time_state_json": {},
            "latest_fees_state_json": {},
            "latest_rules_state_json": {},
        }
        fields.update({key: value for key, value in updates.items() if key in fields})
        conn.execute(
            """
            INSERT INTO mesh_session_state (
                session_id, latest_market_state_json, latest_candidate_state_json,
                latest_position_state_json, latest_risk_state_json, latest_exit_state_json,
                latest_capital_state_json, latest_news_state_json, latest_liquidity_state_json,
                latest_time_state_json, latest_fees_state_json, latest_rules_state_json,
                updated_at
            )
            VALUES (
                %(session_id)s, %(latest_market_state_json)s, %(latest_candidate_state_json)s,
                %(latest_position_state_json)s, %(latest_risk_state_json)s, %(latest_exit_state_json)s,
                %(latest_capital_state_json)s, %(latest_news_state_json)s, %(latest_liquidity_state_json)s,
                %(latest_time_state_json)s, %(latest_fees_state_json)s, %(latest_rules_state_json)s,
                now()
            )
            ON CONFLICT (session_id) DO UPDATE
            SET latest_market_state_json = CASE WHEN EXCLUDED.latest_market_state_json <> '{}'::jsonb THEN EXCLUDED.latest_market_state_json ELSE mesh_session_state.latest_market_state_json END,
                latest_candidate_state_json = CASE WHEN EXCLUDED.latest_candidate_state_json <> '{}'::jsonb THEN EXCLUDED.latest_candidate_state_json ELSE mesh_session_state.latest_candidate_state_json END,
                latest_position_state_json = CASE WHEN EXCLUDED.latest_position_state_json <> '{}'::jsonb THEN EXCLUDED.latest_position_state_json ELSE mesh_session_state.latest_position_state_json END,
                latest_risk_state_json = CASE WHEN EXCLUDED.latest_risk_state_json <> '{}'::jsonb THEN EXCLUDED.latest_risk_state_json ELSE mesh_session_state.latest_risk_state_json END,
                latest_exit_state_json = CASE WHEN EXCLUDED.latest_exit_state_json <> '{}'::jsonb THEN EXCLUDED.latest_exit_state_json ELSE mesh_session_state.latest_exit_state_json END,
                latest_capital_state_json = CASE WHEN EXCLUDED.latest_capital_state_json <> '{}'::jsonb THEN EXCLUDED.latest_capital_state_json ELSE mesh_session_state.latest_capital_state_json END,
                latest_news_state_json = CASE WHEN EXCLUDED.latest_news_state_json <> '{}'::jsonb THEN EXCLUDED.latest_news_state_json ELSE mesh_session_state.latest_news_state_json END,
                latest_liquidity_state_json = CASE WHEN EXCLUDED.latest_liquidity_state_json <> '{}'::jsonb THEN EXCLUDED.latest_liquidity_state_json ELSE mesh_session_state.latest_liquidity_state_json END,
                latest_time_state_json = CASE WHEN EXCLUDED.latest_time_state_json <> '{}'::jsonb THEN EXCLUDED.latest_time_state_json ELSE mesh_session_state.latest_time_state_json END,
                latest_fees_state_json = CASE WHEN EXCLUDED.latest_fees_state_json <> '{}'::jsonb THEN EXCLUDED.latest_fees_state_json ELSE mesh_session_state.latest_fees_state_json END,
                latest_rules_state_json = CASE WHEN EXCLUDED.latest_rules_state_json <> '{}'::jsonb THEN EXCLUDED.latest_rules_state_json ELSE mesh_session_state.latest_rules_state_json END,
                updated_at = now()
            """,
            {
                "session_id": session_id,
                **{key: Jsonb(value) for key, value in fields.items()},
            },
        )

    def list_unlinked_events(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT e.*
                FROM neural_events e
                LEFT JOIN mesh_session_events se ON se.event_id = e.event_id
                WHERE se.id IS NULL
                ORDER BY e.created_at DESC, e.id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def dashboard_summary(self, conn: Connection, *, limit: int = 20, stale_after: timedelta) -> dict[str, Any]:
        counts = conn.execute(
            """
            SELECT
                COUNT(*) AS total_sessions,
                COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active_sessions,
                COUNT(*) FILTER (WHERE session_type = 'MARKET_SESSION') AS market_sessions,
                COUNT(*) FILTER (WHERE session_type = 'CANDIDATE_SESSION') AS candidate_sessions,
                COUNT(*) FILTER (WHERE session_type = 'POSITION_SESSION') AS position_sessions,
                COUNT(*) FILTER (WHERE session_type = 'OPPORTUNITY_SESSION') AS opportunity_sessions,
                COUNT(*) FILTER (WHERE session_type = 'THREAT_SESSION') AS threat_sessions,
                COUNT(*) FILTER (WHERE session_type = 'GLOBAL_SESSION') AS global_sessions,
                COUNT(*) FILTER (WHERE session_type = 'UNASSIGNED_SESSION') AS unassigned_sessions,
                COUNT(*) FILTER (WHERE event_count > 1) AS sessions_with_multiple_events,
                COUNT(*) FILTER (WHERE participant_count > 1) AS sessions_with_multiple_participants
            FROM mesh_sessions
            """
        ).fetchone()
        orphan = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM neural_events e
            LEFT JOIN mesh_session_events se ON se.event_id = e.event_id
            WHERE se.id IS NULL
            """
        ).fetchone()
        coverage = conn.execute(
            """
            SELECT
                COUNT(DISTINCT e.event_id) AS total_events,
                COUNT(DISTINCT se.event_id) AS linked_events
            FROM neural_events e
            LEFT JOIN mesh_session_events se ON se.event_id = e.event_id
            """
        ).fetchone()
        latest = self._list_sessions(conn, limit=limit, order="last_event_at DESC NULLS LAST, id DESC")
        top_active = self._list_sessions(conn, limit=limit, where="status = 'ACTIVE'", order="event_count DESC, participant_count DESC, last_event_at DESC NULLS LAST")
        stale_seconds = int(stale_after.total_seconds())
        stale = self._list_sessions(
            conn,
            limit=limit,
            where=f"(status = 'STALE' OR (status IN ('OPEN', 'ACTIVE') AND last_event_at < now() - interval '{stale_seconds} seconds'))",
            order="last_event_at DESC NULLS LAST, id DESC",
        )
        total_events = int(coverage["total_events"] or 0)
        linked_events = int(coverage["linked_events"] or 0)
        return {
            **{key: int(counts[key] or 0) for key in counts.keys()},
            "latest_sessions": latest,
            "top_active_sessions": top_active,
            "stale_sessions": stale,
            "orphan_events_without_session": int(orphan["count"] or 0),
            "event_to_session_coverage": {
                "total_events": total_events,
                "linked_events": linked_events,
                "coverage_pct": round((linked_events / total_events) * 100, 2) if total_events else 100.0,
            },
        }

    def session_detail(self, conn: Connection, session_id: str, *, limit: int = 100) -> dict[str, Any] | None:
        session = self.get_session(conn, session_id)
        if not session:
            return None
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT se.*, e.market_id, e.candidate_id, e.position_id, e.payload_json, e.created_at AS event_created_at
                FROM mesh_session_events se
                LEFT JOIN neural_events e ON e.event_id = se.event_id
                WHERE se.session_id = %s
                ORDER BY se.linked_at ASC, se.id ASC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]
        participants = [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_session_participants
                WHERE session_id = %s
                ORDER BY last_seen_at DESC, id DESC
                """,
                (session_id,),
            ).fetchall()
        ]
        state = conn.execute("SELECT * FROM mesh_session_state WHERE session_id = %s", (session_id,)).fetchone()
        dialogue = []
        if table_exists(conn, "brain_dialogue_events"):
            dialogue = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT *
                    FROM brain_dialogue_events
                    WHERE (source_table IN ('mesh_sessions', 'mesh_session_events') AND source_record_id = %s)
                       OR raw_payload_json->>'session_id' = %s
                    ORDER BY timestamp DESC, id DESC
                    LIMIT %s
                    """,
                    (session_id, session_id, limit),
                ).fetchall()
            ]
        return {
            "session": session,
            "linked_events": events,
            "participants": participants,
            "latest_state": dict(state) if state else {},
            "dialogue_messages": dialogue,
            "event_timeline": events,
        }

    def _list_sessions(self, conn: Connection, *, limit: int, order: str, where: str | None = None) -> list[dict[str, Any]]:
        where_sql = f"WHERE {where}" if where else ""
        return [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM mesh_sessions
                {where_sql}
                ORDER BY {order}
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None
