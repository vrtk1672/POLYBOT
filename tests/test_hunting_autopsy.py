from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.hunting_autopsy import HuntingAutopsyService


def test_hunting_autopsy_reports_continuity_and_bottleneck(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO runtime_cycles_v2 (cycle_id, mode, status, started_at, finished_at, metadata_json)
            VALUES ('cycle-complete', 'PAPER', 'COMPLETED', now() - interval '3 minutes', now() - interval '2 minutes', '{}'::jsonb)
            """
        )
        conn.execute(
            """
            INSERT INTO proactive_candidate_seeds (
                proactive_candidate_seed_id, market_id, side, seed_state,
                research_only, execution_allowed, paper_allowed, shadow_allowed, live_allowed,
                created_at, updated_at
            )
            VALUES ('seed-hunt', 'market-hunt', 'YES', 'READY', true, false, false, false, false, now(), now())
            """
        )
        conn.execute(
            """
            INSERT INTO paper_runtime_decision_runs (
                run_id, status, started_at, finished_at, candidates_reviewed,
                enter_count, watch_count, blocked_count, metadata_json, created_at
            )
            VALUES ('run-hunt', 'OK', now() - interval '1 minute', now(), 2, 2, 0, 0, '{}'::jsonb, now())
            """
        )
        _runtime_decision(conn, "decision-yes", "market-conflict", "YES", "ENTER", [])
        _runtime_decision(conn, "decision-no", "market-conflict", "NO", "ENTER", [])
        conn.execute(
            """
            INSERT INTO no_trade_log (
                no_trade_id, market_id, side, decision_status, primary_reason,
                reasons_json, blockers, missing_requirements, evidence,
                source_layer, explanation, created_at, updated_at
            )
            VALUES
              ('nt-yes', 'market-conflict', 'YES', 'NO_TRADE', 'SAME_MARKET_OPPOSING_ENTER_CONFLICT',
               '[]'::jsonb, '["SAME_MARKET_OPPOSING_ENTER_CONFLICT"]'::jsonb, '[]'::jsonb,
               '{"paper_session_id":"session-hunt","bridge_outcome":"BLOCKED_BY_DUPLICATE"}'::jsonb,
               'paper_intent_gate', 'Opposing ENTER sides require arbitration.', now(), now()),
              ('nt-no', 'market-conflict', 'NO', 'NO_TRADE', 'SAME_MARKET_OPPOSING_ENTER_CONFLICT',
               '[]'::jsonb, '["SAME_MARKET_OPPOSING_ENTER_CONFLICT"]'::jsonb, '[]'::jsonb,
               '{"paper_session_id":"session-hunt","bridge_outcome":"BLOCKED_BY_DUPLICATE"}'::jsonb,
               'paper_intent_gate', 'Opposing ENTER sides require arbitration.', now(), now())
            """
        )

    payload = HuntingAutopsyService().get_autopsy()

    assert payload["status"] == "OK"
    assert payload["runtime_continuity_verdict"] in {"CONTINUOUS", "PARTIAL"}
    assert payload["primary_bottleneck"] == "SAME_MARKET_OPPOSING_ENTER_CONFLICT"
    assert payload["decision_diversity"]["opposing_enter_markets"]


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_runtime_decisions",
            "paper_runtime_decision_runs",
            "proactive_candidate_seeds",
            "runtime_cycles_v2",
            "paper_sessions",
            "no_trade_log",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance, current_balance_snapshot,
                realized_pnl, unrealized_pnl, net_pnl, status, started_at
            )
            VALUES ('session-hunt', 'pytest', 1000, 1000, 0, 0, 0, 'ACTIVE', now() - interval '5 minutes')
            """
        )


def _runtime_decision(conn, decision_id: str, market_id: str, side: str, decision: str, blockers: list[str]) -> None:
    conn.execute(
        """
        INSERT INTO paper_runtime_decisions (
            decision_id, source_type, candidate_source, source_review_id,
            market_id, condition_id, side, token_id, decision, decision_mode,
            execution_mode, paper_enter_allowed, live_enter_allowed, edge_state,
            thesis_state, opportunity_score, risk_state, capital_state,
            exit_state, lifecycle_state, orderbook_state, token_verification_state,
            candidate_event_scope_state, lineage_state, research_lineage,
            warnings_json, blockers_json, required_to_pass_json, policy_json,
            evidence, is_current_batch, diversity_score, created_at, updated_at
        )
        VALUES (
            %s, 'PROACTIVE_SEED_MESH', 'PROACTIVE_SEED_MESH', %s,
            %s, %s, %s, %s, %s, 'PAPER',
            'PAPER', %s, false, 'EDGE_SUPPORTED',
            'THESIS_SUPPORTED', 61.99, 'RISK_OK', 'CAPITAL_WATCH',
            'EXIT_READY', 'DATA_ONLY_RESEARCH', 'FRESH', 'TOKENS_VERIFIED',
            'CANDIDATE_SCOPED', 'COMPLETE', '{}'::jsonb,
            '[]'::jsonb, %s, '[]'::jsonb, '{}'::jsonb,
            '{}'::jsonb, true, 120, now(), now()
        )
        """,
        (
            decision_id,
            f"review-{decision_id}",
            market_id,
            f"condition-{market_id}",
            side,
            f"token-{market_id}-{side}",
            decision,
            decision == "ENTER" and not blockers,
            Jsonb(blockers),
        ),
    )


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])
