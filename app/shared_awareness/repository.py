from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.shared_awareness.types import ALL_DOMAINS, DOMAIN_STATE_COLUMNS, AwarenessDomain


class SharedAwarenessRepository:
    def get_session(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_sessions WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def list_sessions(self, conn: Connection, *, limit: int = 100) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_sessions
                WHERE status IN ('OPEN', 'ACTIVE', 'STALE')
                ORDER BY last_event_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def linked_events(self, conn: Connection, session_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT se.role, se.linked_at, e.*
                FROM mesh_session_events se
                JOIN neural_events e ON e.event_id = se.event_id
                WHERE se.session_id = %s
                ORDER BY se.linked_at DESC, se.id DESC
                LIMIT %s
                """,
                (session_id, limit),
            ).fetchall()
        ]

    def participants(self, conn: Connection, session_id: str) -> list[dict[str, Any]]:
        return [
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

    def upsert_awareness(self, conn: Connection, *, awareness: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
        state_values = {column: Jsonb(awareness[column]) for column in DOMAIN_STATE_COLUMNS.values()}
        row = conn.execute(
            """
            INSERT INTO mesh_shared_awareness (
                awareness_id, session_id, session_type, market_id, candidate_id, position_id,
                status, freshness_status, completeness_score, confidence_score,
                news_state_json, whale_state_json, social_state_json, rules_state_json,
                liquidity_state_json, orderbook_state_json, fees_state_json, time_state_json,
                risk_state_json, exit_state_json, capital_state_json, pnl_state_json,
                memory_state_json, position_state_json, candidate_state_json,
                missing_domains_json, stale_domains_json, source_counts_json, updated_at
            )
            VALUES (
                %(awareness_id)s, %(session_id)s, %(session_type)s, %(market_id)s, %(candidate_id)s, %(position_id)s,
                %(status)s, %(freshness_status)s, %(completeness_score)s, %(confidence_score)s,
                %(news_state_json)s, %(whale_state_json)s, %(social_state_json)s, %(rules_state_json)s,
                %(liquidity_state_json)s, %(orderbook_state_json)s, %(fees_state_json)s, %(time_state_json)s,
                %(risk_state_json)s, %(exit_state_json)s, %(capital_state_json)s, %(pnl_state_json)s,
                %(memory_state_json)s, %(position_state_json)s, %(candidate_state_json)s,
                %(missing_domains_json)s, %(stale_domains_json)s, %(source_counts_json)s, now()
            )
            ON CONFLICT (session_id) DO UPDATE
            SET session_type = EXCLUDED.session_type,
                market_id = EXCLUDED.market_id,
                candidate_id = EXCLUDED.candidate_id,
                position_id = EXCLUDED.position_id,
                status = EXCLUDED.status,
                freshness_status = EXCLUDED.freshness_status,
                completeness_score = EXCLUDED.completeness_score,
                confidence_score = EXCLUDED.confidence_score,
                news_state_json = EXCLUDED.news_state_json,
                whale_state_json = EXCLUDED.whale_state_json,
                social_state_json = EXCLUDED.social_state_json,
                rules_state_json = EXCLUDED.rules_state_json,
                liquidity_state_json = EXCLUDED.liquidity_state_json,
                orderbook_state_json = EXCLUDED.orderbook_state_json,
                fees_state_json = EXCLUDED.fees_state_json,
                time_state_json = EXCLUDED.time_state_json,
                risk_state_json = EXCLUDED.risk_state_json,
                exit_state_json = EXCLUDED.exit_state_json,
                capital_state_json = EXCLUDED.capital_state_json,
                pnl_state_json = EXCLUDED.pnl_state_json,
                memory_state_json = EXCLUDED.memory_state_json,
                position_state_json = EXCLUDED.position_state_json,
                candidate_state_json = EXCLUDED.candidate_state_json,
                missing_domains_json = EXCLUDED.missing_domains_json,
                stale_domains_json = EXCLUDED.stale_domains_json,
                source_counts_json = EXCLUDED.source_counts_json,
                updated_at = now()
            RETURNING *
            """,
            {
                **awareness,
                **state_values,
                "missing_domains_json": Jsonb(awareness["missing_domains_json"]),
                "stale_domains_json": Jsonb(awareness["stale_domains_json"]),
                "source_counts_json": Jsonb(awareness["source_counts_json"]),
            },
        ).fetchone()
        assert row is not None
        conn.execute("DELETE FROM mesh_awareness_sources WHERE awareness_id = %s", (awareness["awareness_id"],))
        for source in sources:
            conn.execute(
                """
                INSERT INTO mesh_awareness_sources (
                    awareness_id, session_id, source_domain, source_table, source_record_id,
                    source_component, source_created_at, freshness_status, contribution_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (awareness_id, source_domain, source_table, source_record_id) DO NOTHING
                """,
                (
                    awareness["awareness_id"],
                    awareness["session_id"],
                    source["source_domain"],
                    source["source_table"],
                    source["source_record_id"],
                    source.get("source_component"),
                    source.get("source_created_at"),
                    source["freshness_status"],
                    source["contribution_summary"],
                ),
            )
        self.update_session_state(conn, awareness=awareness)
        return dict(row)

    def update_session_state(self, conn: Connection, *, awareness: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO mesh_session_state (
                session_id,
                latest_candidate_state_json,
                latest_position_state_json,
                latest_risk_state_json,
                latest_exit_state_json,
                latest_capital_state_json,
                latest_news_state_json,
                latest_liquidity_state_json,
                latest_time_state_json,
                latest_fees_state_json,
                latest_rules_state_json,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (session_id) DO UPDATE
            SET latest_candidate_state_json = EXCLUDED.latest_candidate_state_json,
                latest_position_state_json = EXCLUDED.latest_position_state_json,
                latest_risk_state_json = EXCLUDED.latest_risk_state_json,
                latest_exit_state_json = EXCLUDED.latest_exit_state_json,
                latest_capital_state_json = EXCLUDED.latest_capital_state_json,
                latest_news_state_json = EXCLUDED.latest_news_state_json,
                latest_liquidity_state_json = EXCLUDED.latest_liquidity_state_json,
                latest_time_state_json = EXCLUDED.latest_time_state_json,
                latest_fees_state_json = EXCLUDED.latest_fees_state_json,
                latest_rules_state_json = EXCLUDED.latest_rules_state_json,
                updated_at = now()
            """,
            (
                awareness["session_id"],
                Jsonb(awareness["candidate_state_json"]),
                Jsonb(awareness["position_state_json"]),
                Jsonb(awareness["risk_state_json"]),
                Jsonb(awareness["exit_state_json"]),
                Jsonb(awareness["capital_state_json"]),
                Jsonb(awareness["news_state_json"]),
                Jsonb(awareness["liquidity_state_json"]),
                Jsonb(awareness["time_state_json"]),
                Jsonb(awareness["fees_state_json"]),
                Jsonb(awareness["rules_state_json"]),
            ),
        )

    def get_awareness(self, conn: Connection, session_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM mesh_shared_awareness WHERE session_id = %s", (session_id,)).fetchone()
        return dict(row) if row else None

    def sources(self, conn: Connection, awareness_id: str) -> list[dict[str, Any]]:
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

    def dashboard_rows(self, conn: Connection, *, limit: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                """
                SELECT *
                FROM mesh_shared_awareness
                ORDER BY updated_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        ]

    def all_awareness_rows(self, conn: Connection) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute("SELECT * FROM mesh_shared_awareness").fetchall()]

    def detail(self, conn: Connection, session_id: str, *, limit: int = 100) -> dict[str, Any] | None:
        session = self.get_session(conn, session_id)
        awareness = self.get_awareness(conn, session_id)
        if not session or not awareness:
            return None
        events = self.linked_events(conn, session_id, limit=limit)
        participants = self.participants(conn, session_id)
        sources = self.sources(conn, awareness["awareness_id"])
        domains = {domain.value: awareness[DOMAIN_STATE_COLUMNS[domain]] for domain in ALL_DOMAINS}
        return {
            "session": session,
            "awareness": awareness,
            "domains": domains,
            "source_refs": sources,
            "missing_domains": awareness.get("missing_domains_json") or [],
            "stale_domains": awareness.get("stale_domains_json") or [],
            "latest_linked_events": events,
            "participants": participants,
        }


def table_exists(conn: Connection, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()
    return row is not None and row["name"] is not None


def table_columns(conn: Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {
        row["column_name"]
        for row in conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            (table,),
        ).fetchall()
    }
