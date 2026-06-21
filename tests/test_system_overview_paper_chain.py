from __future__ import annotations

from psycopg.types.json import Jsonb

from app.control_center.system_overview import _decisions, derive_execution_mode
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_system_overview_reports_paper_runtime_chain_counts(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM paper_runtime_decisions")
        conn.execute(
            """
            INSERT INTO paper_runtime_decisions (
                decision_id, source_type, candidate_source, market_id, condition_id,
                side, token_id, decision, decision_mode, execution_mode,
                paper_enter_allowed, live_enter_allowed, opportunity_score,
                risk_state, capital_state, exit_state, lifecycle_state,
                orderbook_state, token_verification_state, candidate_event_scope_state,
                lineage_state, blockers_json, warnings_json, required_to_pass_json,
                policy_json, evidence
            )
            VALUES (
                'paper-runtime-enter','PROACTIVE_SEED_MESH','PROACTIVE_SEED_MESH',
                'overview-market','condition-overview','YES','token-overview',
                'ENTER','PAPER','PAPER',true,false,62,
                'RISK_OK','CAPITAL_WATCH','EXIT_READY','DATA_ONLY_RESEARCH',
                'FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED','COMPLETE',
                '[]'::jsonb,%s,'[]'::jsonb,%s,%s
            )
            """,
            (
                Jsonb(["CAPITAL_WATCH_ALLOWED_FOR_PAPER_LEARNING"]),
                Jsonb({"live_enter_allowed": False}),
                Jsonb({"paper_runtime_decision_id": "paper-runtime-enter"}),
            ),
        )
        tables = _table_cache(conn)
        decisions = _decisions(conn, tables)

    assert decisions["runtime_decisions_total"] == 1
    assert decisions["paper_enter_decisions"] == 1
    assert decisions["top_runtime_decisions"][0]["decision"] == "ENTER"


def test_execution_mode_paper_when_governor_mode_is_paper() -> None:
    assert derive_execution_mode(system_power="ON", paper_simulation_enabled=False, runtime_mode="PAPER") == "PAPER"
    assert derive_execution_mode(system_power="ON", paper_simulation_enabled=False, runtime_mode="DATA_ONLY") == "DATA_ONLY"
    assert derive_execution_mode(system_power="OFF", paper_simulation_enabled=True, runtime_mode="PAPER") == "DISABLED"


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
