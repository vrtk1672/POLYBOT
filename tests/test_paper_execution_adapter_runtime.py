from __future__ import annotations

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.runtime.modes import RuntimeAction
from app.services.paper_execution import PaperExecutionService


class _Power:
    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON", "runtime_work_allowed": True}


class _Governor:
    def can_execute(self, action, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value == RuntimeAction.RUN_PAPER_SIMULATION.value


def test_runtime_decision_intent_executes_without_live_order(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in ("paper_execution_runs", "paper_capital_ledger", "paper_fills", "paper_positions", "paper_orders", "paper_signals", "paper_runs", "paper_intents", "orderbook_snapshots"):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        if _table_exists(conn, "paper_sessions"):
            conn.execute("DELETE FROM paper_session_resets")
            conn.execute("DELETE FROM paper_sessions")
            conn.execute(
                """
                INSERT INTO paper_sessions (
                    paper_session_id, session_name, starting_balance,
                    current_balance_snapshot, realized_pnl, unrealized_pnl,
                    net_pnl, status, started_at, created_by, metadata_json
                )
                VALUES ('paper-session-runtime-test','Runtime Test Session',1000,1000,0,0,0,'ACTIVE',now(),'test','{}'::jsonb)
                """
            )
        now = datetime.now(UTC)
        snapshot_id = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES ('adapter-book','adapter-market','adapter-token','YES',0.50,0.52,0.02,0.51,0.8,'test','OK',false,%s,%s,%s)
            RETURNING id
            """,
            (now, now, now),
        ).fetchone()["id"]
        conn.execute(
            """
                INSERT INTO paper_intents (
                    paper_intent_id, eligibility_id, thesis_id, risk_decision_id, exit_plan_id,
                    market_id, side, price_basis, orderbook_snapshot_id, intended_price,
                    max_slippage, confidence, intent_status, intent_type, intent_reason,
                    evidence, blockers, paper_only, live, execution_allowed,
                    order_intent_created, generated_by, producer_name, is_runtime_generated,
                    is_dry_run_generated, paper_session_id, created_at, updated_at
                )
                VALUES (
                    'paper_intent_runtime_adapter','runtime-decision','paper-runtime-thesis',
                    'paper-runtime-risk','paper-runtime-exit','adapter-market','YES',
                    'ORDERBOOK_BEST_ASK',%s,0.52,0.02,0.62,'CREATED','PAPER_ENTRY_INTENT',
                    'Unified PAPER runtime decision passed Paper Intent Gate; PAPER adapter only.',
                    %s,'[]'::jsonb,true,false,false,false,'runtime','paper_intent_gate',true,false,
                    'paper-session-runtime-test',%s,%s
                )
            """,
            (
                snapshot_id,
                Jsonb(
                    {
                        "quantity": 1.0,
                        "paper_runtime_decision_id": "runtime-decision",
                        "paper_mode_policy": {"paper_enter_allowed": True, "blockers": [], "warnings": ["CAPITAL_WATCH_ALLOWED_FOR_PAPER_LEARNING"]},
                        "paper_runtime_decision": {"decision_id": "runtime-decision", "paper_enter_allowed": True, "blockers_json": []},
                    }
                ),
                now,
                now,
            ),
        )

    result = PaperExecutionService(system_power=_Power(), governor=_Governor()).run_execution(correlation_id="adapter-runtime")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 1
        assert _count(conn, "paper_fills") == 1
        assert _count(conn, "paper_positions") == 1
        assert conn.execute("SELECT paper_session_id FROM paper_orders LIMIT 1").fetchone()["paper_session_id"] == "paper-session-runtime-test"
        assert conn.execute("SELECT paper_session_id FROM paper_fills LIMIT 1").fetchone()["paper_session_id"] == "paper-session-runtime-test"
        assert conn.execute("SELECT paper_session_id FROM paper_positions LIMIT 1").fetchone()["paper_session_id"] == "paper-session-runtime-test"
        assert _count(conn, "live_orders") == 0


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"])


def _count(conn, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0)
