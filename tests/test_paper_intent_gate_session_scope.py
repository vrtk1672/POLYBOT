from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from decision_autopsy_helpers import SESSION_ID, prepare_autopsy_fixture, seed_runtime_decision


def test_previous_session_intent_does_not_block_current_session_enter(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-reused-enter",
        market_id="market-reused",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance,
                current_balance_snapshot, realized_pnl, unrealized_pnl,
                net_pnl, status, started_at, closed_at, closed_reason,
                created_by, metadata_json
            )
            VALUES ('previous-session','Previous',1000,1000,0,0,0,'ARCHIVED',%s,%s,
                    'TEST','test','{}'::jsonb)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, intended_price,
                max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live,
                execution_allowed, order_intent_created, generated_by,
                producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at, paper_session_id
            )
            VALUES ('paper_intent_decision-reused-enter','decision-reused-enter',
                    'thesis','risk','exit','market-reused','YES',
                    'ORDERBOOK_BEST_ASK',0.42,0.02,0.7,'CREATED',
                    'PAPER_ENTRY_INTENT','old',%s,'[]'::jsonb,true,false,false,
                    false,'test','test',true,false,%s,%s,'previous-session')
            """,
            (Jsonb({"paper_runtime_decision_id": "decision-reused-enter"}), now, now),
        )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            """
            SELECT paper_intent_id, paper_session_id
            FROM paper_intents
            WHERE market_id = 'market-reused' AND side = 'YES'
            ORDER BY paper_session_id
            """
        ).fetchall()
    assert {row["paper_session_id"] for row in rows} == {"previous-session", SESSION_ID}


def test_current_session_active_intent_blocks_duplicate(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    seed_runtime_decision(
        decision_id="decision-current-duplicate",
        market_id="market-dup",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, intended_price,
                max_slippage, confidence, intent_status, intent_type,
                intent_reason, evidence, blockers, paper_only, live,
                execution_allowed, order_intent_created, generated_by,
                producer_name, is_runtime_generated, is_dry_run_generated,
                created_at, updated_at, paper_session_id
            )
            VALUES ('existing-current-intent','existing','thesis','risk','exit',
                    'market-dup','YES','ORDERBOOK_BEST_ASK',0.42,0.02,0.7,
                    'CREATED','PAPER_ENTRY_INTENT','current','{}'::jsonb,
                    '[]'::jsonb,true,false,false,false,'test','test',true,false,
                    %s,%s,%s)
            """,
            (now, now, SESSION_ID),
        )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        no_trade = conn.execute(
            """
            SELECT blockers
            FROM no_trade_log
            WHERE market_id = 'market-dup' AND side = 'YES'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
    assert no_trade is not None
    assert "DUPLICATE_ACTIVE_PAPER_INTENT" in no_trade["blockers"] or "SAME_MARKET_SAME_SIDE_ACTIVE_INTENT_BLOCK" in no_trade["blockers"]
