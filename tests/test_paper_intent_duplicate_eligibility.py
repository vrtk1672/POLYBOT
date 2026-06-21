from __future__ import annotations

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_intents import PaperIntentGateService

from decision_autopsy_helpers import SESSION_ID, prepare_autopsy_fixture, seed_runtime_decision


def test_previous_session_unscoped_runtime_eligibility_does_not_block_new_session(postgres_test_schema) -> None:
    prepare_autopsy_fixture()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_sessions (
                paper_session_id, session_name, starting_balance, current_balance_snapshot,
                realized_pnl, unrealized_pnl, net_pnl, status, started_at,
                closed_at, closed_reason, created_by, metadata_json
            )
            VALUES (
                'previous-session','Previous',1000,1000,0,0,0,'ARCHIVED',
                now() - interval '1 hour', now(), 'RESET_ARCHIVED', 'test', '{}'::jsonb
            )
            """
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
                paper_session_id
            )
            VALUES (
                'paper_intent_paper_runtime_decision_cross_session',
                'paper_runtime_decision_cross_session',
                'thesis','risk','exit','market-cross','YES','ORDERBOOK_MID',
                0.42,0.02,0.7,'CREATED','PAPER_ENTRY_INTENT','previous',
                %s,'[]'::jsonb,true,false,false,false,'runtime',
                'paper_intent_gate',true,false,'previous-session'
            )
            """,
            (Jsonb({"paper_runtime_decision_id": "paper_runtime_decision_cross_session"}),),
        )
    seed_runtime_decision(
        decision_id="paper_runtime_decision_cross_session",
        market_id="market-cross",
        side="YES",
        decision="ENTER",
        score=61.99,
        blockers=[],
    )

    result = PaperIntentGateService().build_intents(limit=10)

    assert result["paper_intents_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        rows = conn.execute(
            """
            SELECT paper_intent_id, eligibility_id, paper_session_id
            FROM paper_intents
            WHERE market_id='market-cross'
            ORDER BY created_at ASC
            """
        ).fetchall()
    assert len(rows) == 2
    assert rows[-1]["paper_session_id"] == SESSION_ID
    assert rows[-1]["eligibility_id"].startswith("paper_runtime_decision_")
    assert rows[-1]["eligibility_id"].endswith(f"_{SESSION_ID}")
    assert rows[-1]["eligibility_id"] != "paper_runtime_decision_cross_session"
