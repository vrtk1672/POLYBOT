from __future__ import annotations

from psycopg.types.json import Jsonb

from app.control_center.system_overview import _decisions
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_system_overview_exposes_last_mile_refresh_diagnostics(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("last_mile_orderbook_refresh_attempts", "paper_runtime_decisions"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_runtime_decisions (
                decision_id, source_type, candidate_source, market_id, condition_id,
                side, token_id, decision, decision_mode, execution_mode,
                paper_enter_allowed, live_enter_allowed, opportunity_score,
                orderbook_state, orderbook_snapshot_id, orderbook_age_seconds,
                orderbook_ttl_seconds, last_mile_refresh_attempted,
                last_mile_refresh_state, last_mile_refresh_error,
                post_refresh_orderbook_state, risk_state, capital_state,
                exit_state, lifecycle_state, token_verification_state,
                candidate_event_scope_state, lineage_state, blockers_json,
                warnings_json, required_to_pass_json, policy_json, evidence
            )
            VALUES (
                'decision-stale','PROACTIVE_SEED_MESH','PROACTIVE_SEED_MESH',
                'market-a','condition-a','YES','token-yes',
                'BLOCK','PAPER','PAPER',false,false,62,
                'FRESH',123,240,180,true,'FAILED','ORDERBOOK_CONNECTOR_ERROR',
                'STALE_OR_MISSING','RISK_OK','CAPITAL_WATCH','EXIT_READY',
                'DATA_ONLY_RESEARCH','TOKENS_VERIFIED','CANDIDATE_SCOPED',
                'COMPLETE',%s,'[]'::jsonb,'[]'::jsonb,'{}'::jsonb,'{}'::jsonb
            )
            """,
            (Jsonb(["ORDERBOOK_CONNECTOR_ERROR"]),),
        )
        conn.execute(
            """
            INSERT INTO last_mile_orderbook_refresh_attempts (
                attempt_id, decision_id, market_id, condition_id, token_id, side,
                refresh_state, refresh_error, orderbook_ttl_seconds,
                stale_cleared, started_at, completed_at
            )
            VALUES (
                'attempt-a','decision-stale','market-a','condition-a','token-yes','YES',
                'FAILED','ORDERBOOK_CONNECTOR_ERROR',180,false,now(),now()
            )
            """
        )
        tables = _table_cache(conn)
        decisions = _decisions(conn, tables)

    assert decisions["stale_orderbook_blocked_count"] == 1
    assert decisions["last_mile_refresh_attempts"] == 1
    assert decisions["last_mile_refresh_failed_count"] == 1
    top = decisions["top_runtime_decisions"][0]
    assert top["orderbook_ttl_seconds"] == 180
    assert top["last_mile_refresh_state"] == "FAILED"
    assert top["last_mile_refresh_error"] == "ORDERBOOK_CONNECTOR_ERROR"


def _table_cache(conn) -> dict[str, set[str]]:
    rows = conn.execute(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema=current_schema()
        """
    ).fetchall()
    cache: dict[str, set[str]] = {}
    for row in rows:
        cache.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    return cache


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
