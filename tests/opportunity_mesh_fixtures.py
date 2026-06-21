from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations

SESSION_ID = "opportunity-mesh-session"


def prepare_opportunity_mesh_fixture(*, defense_level: int = 20) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "opportunity_reactivation_events",
            "opportunity_memory",
            "paper_position_closes",
            "paper_positions",
            "paper_fills",
            "paper_orders",
            "paper_execution_runs",
            "paper_learning_ledger",
            "paper_intents",
            "paper_runtime_decisions",
            "paper_session_resets",
            "paper_sessions",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance, current_balance_snapshot,
                realized_pnl, unrealized_pnl, net_pnl, status, started_at,
                defense_level, max_deployed_pct, max_single_trade_pct, metadata_json
            )
            VALUES (%s, 'Opportunity Mesh Test', 1000, 1000, 0, 0, 0, 'ACTIVE',
                    now() - interval '10 minutes', %s, 80, 15, '{}'::jsonb)
            """,
            (SESSION_ID, defense_level),
        )


def seed_runtime_decision(
    *,
    decision_id: str,
    market_id: str,
    side: str = "YES",
    decision: str = "ENTER",
    blockers: list[str] | None = None,
    paper_enter_allowed: bool | None = None,
    score: float = 55.46,
    evidence: dict[str, Any] | None = None,
) -> None:
    blockers = blockers or []
    if paper_enter_allowed is None:
        paper_enter_allowed = decision == "ENTER" and not blockers
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
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
                'THESIS_SUPPORTED', %s, 'RISK_OK', 'CAPITAL_WATCH',
                'EXIT_READY', 'DATA_ONLY_RESEARCH', 'FRESH', 'TOKENS_VERIFIED',
                'CANDIDATE_SCOPED', 'COMPLETE', '{}'::jsonb,
                '[]'::jsonb, %s, '[]'::jsonb, '{}'::jsonb,
                %s, true, 100, now(), now()
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
                paper_enter_allowed,
                score,
                Jsonb(blockers),
                Jsonb(evidence or {}),
            ),
        )


def seed_paper_intent(
    *,
    intent_id: str,
    eligibility_id: str,
    market_id: str,
    side: str = "YES",
    runtime_decision_id: str | None = None,
    status: str = "CREATED",
    seconds_old: int = 0,
    execution_block_reason: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    created_at = datetime.now(UTC) - timedelta(seconds=seconds_old)
    intent_evidence: dict[str, Any] = {"quantity": 1.0}
    if evidence:
        intent_evidence.update(evidence)
    if runtime_decision_id:
        intent_evidence["paper_runtime_decision_id"] = runtime_decision_id
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                market_id, side, price_basis, intended_price, max_slippage, confidence,
                intent_status, intent_type, intent_reason, evidence, blockers,
                paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated,
                paper_session_id, execution_block_reason, created_at, updated_at
            )
            VALUES (
                %s, %s, 'thesis', 'risk', 'exit',
                %s, %s, 'ORDERBOOK_BEST_ASK', 0.50, 0.02, 0.62,
                %s, 'PAPER_ENTRY_INTENT', 'test intent', %s, '[]'::jsonb,
                true, false, false, false,
                'test', 'paper_intent_gate', true, false,
                %s, %s, %s, %s
            )
            """,
            (
                intent_id,
                eligibility_id,
                market_id,
                side,
                status,
                Jsonb(intent_evidence),
                SESSION_ID,
                execution_block_reason,
                created_at,
                created_at,
            ),
        )


def table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
