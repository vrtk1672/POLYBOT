from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.hunting_autopsy import HuntingAutopsyService


def test_post_trade_rehunt_reports_work_after_close(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_position_closes",
            "paper_positions",
            "paper_runs",
            "paper_sessions",
            "paper_runtime_decision_runs",
            "paper_intent_runs",
            "proactive_candidate_seeds",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance, current_balance_snapshot,
                realized_pnl, unrealized_pnl, net_pnl, status, started_at
            )
            VALUES ('session-rehunt', 'pytest', 1000, 1000, 0, 0, 0, 'ACTIVE', now() - interval '30 minutes')
            """
        )
        conn.execute(
            """
            INSERT INTO paper_runs (id, mode, started_at, ended_at, status, metadata_json, paper_session_id)
            VALUES (
                '00000000-0000-0000-0000-000000000001',
                'PAPER',
                now() - interval '20 minutes',
                now() - interval '15 minutes',
                'COMPLETED',
                '{}'::jsonb,
                'session-rehunt'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                current_status, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, paper_session_id
            )
            VALUES ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'market-rehunt', 'YES', 1, 0.5, 'CLOSED',
                    'THESIS_SUPPORTED', 'VALID',
                    now() - interval '20 minutes', now() - interval '15 minutes',
                    now() - interval '15 minutes', 'session-rehunt')
            """
        )
        position_id = conn.execute("SELECT id FROM paper_positions WHERE market_id='market-rehunt'").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO paper_position_closes (
                close_id, position_id, market_id, side, entry_price, exit_price,
                quantity, realized_pnl, exit_reason, price_basis, source_exit_price,
                created_at, paper_session_id
            )
            VALUES ('close-rehunt', %s, 'market-rehunt', 'YES', 0.5, 0.55,
                    1, 0.05, 'TAKE_PROFIT', 'BEST_BID', '0.55',
                    now() - interval '15 minutes', 'session-rehunt')
            """,
            (position_id,),
        )
        conn.execute(
            """
            INSERT INTO proactive_candidate_seeds (
                proactive_candidate_seed_id, market_id, side, seed_state,
                research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed,
                created_at, updated_at
            )
            VALUES ('seed-after-close', 'market-next', 'NO', 'READY', true, false, false, false, false, now(), now())
            """
        )
        conn.execute(
            """
            INSERT INTO paper_runtime_decision_runs (
                run_id, status, started_at, finished_at, candidates_reviewed,
                enter_count, watch_count, blocked_count, metadata_json, created_at
            )
            VALUES ('runtime-after-close', 'OK', now() - interval '1 minute', now(), 1, 0, 1, 0, '{}'::jsonb, now())
            """
        )
        conn.execute(
            """
            INSERT INTO paper_intent_runs (
                run_id, status, candidates_checked, no_trade_records_created,
                blocked_candidates, started_at, finished_at, created_at
            )
            VALUES ('intent-after-close', 'OK', 1, 1, 1, now() - interval '1 minute', now(), now())
            """
        )

    payload = HuntingAutopsyService().get_autopsy()

    assert payload["post_trade_rehunt"]["returns_to_hunting"] is True
    assert payload["post_trade_rehunt"]["candidate_generation_after_trade"] >= 1
    assert payload["post_trade_rehunt"]["intent_gate_runs_after_trade"] >= 1


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
