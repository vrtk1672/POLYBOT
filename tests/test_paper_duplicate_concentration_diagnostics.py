from __future__ import annotations

from psycopg.types.json import Jsonb

from app.control_center.system_overview import _decisions
from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


def test_duplicate_concentration_diagnostics_are_exposed(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM paper_runtime_decisions")
        for idx in range(3):
            conn.execute(
                """
                INSERT INTO paper_runtime_decisions (
                    decision_id, source_type, candidate_source, market_id, condition_id,
                    side, token_id, decision, decision_mode, execution_mode,
                    paper_enter_allowed, live_enter_allowed, opportunity_score,
                    risk_state, capital_state, exit_state, lifecycle_state,
                    orderbook_state, token_verification_state, candidate_event_scope_state,
                    lineage_state, blockers_json, warnings_json, required_to_pass_json,
                    diversity_score, duplicate_suppressed_count, is_current_batch,
                    policy_json, evidence
                )
                VALUES (
                    %s,'PROACTIVE_SEED_MESH','PROACTIVE_SEED_MESH',
                    'diag-market','condition-diag','YES','token-diag',
                    'BLOCK','PAPER','PAPER',false,false,62,
                    'RISK_OK','CAPITAL_WATCH','EXIT_READY','DATA_ONLY_RESEARCH',
                    'FRESH','TOKENS_VERIFIED','CANDIDATE_SCOPED','COMPLETE',
                    %s,'[]'::jsonb,'[]'::jsonb,62,0,true,%s,%s
                )
                """,
                (
                    f"diag-decision-{idx}",
                    Jsonb(["SAME_MARKET_DUPLICATE_DECISION"] if idx else []),
                    Jsonb({"live_enter_allowed": False}),
                    Jsonb({"diversity": {"trigger_type": "MARKET_MOVEMENT"}}),
                ),
            )
        tables = _table_cache(conn)
        decisions = _decisions(conn, tables)

    assert decisions["unique_market_count"] == 1
    assert decisions["unique_side_count"] == 1
    assert decisions["concentration_score"] == 1.0
    assert decisions["runtime_decisions_by_market"]["diag-market"] == 3
    assert decisions["runtime_decisions_by_trigger_family"]["MARKET_MOVEMENT"] == 3
    assert decisions["top_duplicate_blockers_by_market_side"] == ["diag-market YES: 3"]


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
