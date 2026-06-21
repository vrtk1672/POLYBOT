from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations

OLD_RUN_ID = "11111111-1111-4111-8111-111111111111"
OLD_SIGNAL_ID = "22222222-2222-4222-8222-222222222222"
OLD_ORDER_ID = "33333333-3333-4333-8333-333333333333"
OLD_POSITION_ID = "44444444-4444-4444-8444-444444444444"

def prepare_paper_session_fixture() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_session_resets",
            "paper_sessions",
            "paper_position_closes",
            "paper_daily_pnl",
            "paper_capital_ledger",
            "paper_fills",
            "paper_positions",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intents",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, realized_pnl,
                unrealized_pnl, daily_pnl, risk_per_trade_pct, max_position_size,
                max_daily_loss_pct, max_open_positions, max_total_open_exposure_pct,
                status, metadata_json
            )
            VALUES ('paper_default','Default Paper Account','USD',1000,1041,1036,5,5,41,-1,40,1,25,5,3,15,'ACTIVE','{}'::jsonb)
            ON CONFLICT (account_id) DO UPDATE SET
                initial_balance=EXCLUDED.initial_balance,
                current_balance=EXCLUDED.current_balance,
                available_balance=EXCLUDED.available_balance,
                locked_balance=EXCLUDED.locked_balance,
                open_exposure=EXCLUDED.open_exposure,
                realized_pnl=EXCLUDED.realized_pnl,
                unrealized_pnl=EXCLUDED.unrealized_pnl,
                daily_pnl=EXCLUDED.daily_pnl,
                status='ACTIVE',
                updated_at=now()
            """
        )
        now = datetime.now(UTC)
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, intended_price, confidence,
                price_basis, max_slippage, intent_status, intent_type, intent_reason, evidence, blockers,
                paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated,
                is_dry_run_generated, created_at, updated_at
            )
            VALUES ('old-intent','elig','thesis','risk','exit','market-a','YES',0.50,0.7,'ORDERBOOK_MID',0.02,'CREATED','PAPER_ENTRY_INTENT','old','{}'::jsonb,'[]'::jsonb,true,false,false,false,'test','test',true,false,%s,%s)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count,
                signals_emitted_count, metadata_json
            )
            VALUES (%s,'PAPER_SIM',%s,%s,'COMPLETED',1,1,1,1,'{}'::jsonb)
            """,
            (OLD_RUN_ID, now, now),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, confidence, intended_price,
                intended_size, guard_result, reason_code, reason_text,
                payload_json
            )
            VALUES (%s,%s,'market-a','WOULD_ENTER','YES','PAPER_ENTRY','PAPER_INTENT',0.7,0.5,10,'PASS','test','test','{}'::jsonb)
            """,
            (OLD_SIGNAL_ID, OLD_RUN_ID),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, avg_fill_price,
                min_size_check_passed, payload_json
            )
            VALUES (%s,%s,%s,'market-a','YES','BUY',0.50,10,5,'FILLED',1,10,0,0.50,true,'{}'::jsonb)
            """
            ,
            (OLD_ORDER_ID, OLD_RUN_ID, OLD_SIGNAL_ID),
        )
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id,
                side, fill_price, quantity, price_basis, metadata_json
            )
            VALUES ('old-fill',%s,'old-intent','market-a','YES',0.50,10,'TEST','{}'::jsonb)
            """
            ,
            (OLD_ORDER_ID,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                mark_price, unrealized, realized, current_status, thesis_state,
                invalidation_state, opened_at, updated_at, payload_json
            )
            VALUES (%s,%s,'market-a','YES',10,0.50,0.60,1,0,'OPEN','ACTIVE','NONE',%s,%s,%s)
            """,
            (OLD_POSITION_ID, OLD_RUN_ID, now, now, Jsonb({"source_intent_id": "old-intent"})),
        )


def table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
