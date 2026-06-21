from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations


class PowerOn:
    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON", "runtime_work_allowed": True}


class GovernorAllow:
    def can_execute(self, action: Any, metadata: dict[str, Any] | None = None) -> bool:
        return True


class NoRefresh:
    def ensure_fresh(self, conn: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "refresh_state": "FAILED",
            "refresh_error": "ORDERBOOK_CONNECTOR_ERROR",
            "orderbook": None,
            **kwargs,
        }


class StubRefresh:
    def __init__(self, orderbook: dict[str, Any]) -> None:
        self.orderbook = orderbook

    def ensure_fresh(self, conn: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "refresh_state": "REFRESHED_FRESH",
            "refresh_error": None,
            "stale_cleared": True,
            "orderbook": self.orderbook,
            **kwargs,
        }


def prepare_execution_price_fixture(*, defense_level: int = 20) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_capital_ledger",
            "paper_execution_runs",
            "paper_trade_ledger",
            "paper_position_closes",
            "paper_fills",
            "paper_position_events",
            "paper_positions",
            "paper_order_events",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intents",
            "orderbook_snapshots",
            "paper_session_resets",
            "paper_sessions",
        ):
            if table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        if table_exists(conn, "paper_sessions"):
            conn.execute(
                """
                INSERT INTO paper_sessions (
                    paper_session_id, session_name, starting_balance, current_balance_snapshot,
                    realized_pnl, unrealized_pnl, net_pnl, status, started_at,
                    defense_level, max_deployed_pct, max_single_trade_pct, metadata_json
                )
                VALUES ('paper-execution-price-session','Execution Price Test',1000,1000,0,0,0,'ACTIVE',
                        now(), %s, 80, 15, '{}'::jsonb)
                """,
                (defense_level,),
            )


def seed_orderbook(
    *,
    snapshot_ref: str,
    market_id: str = "price-market",
    token_id: str = "price-token-yes",
    side: str = "YES",
    best_bid: str = "0.50",
    best_ask: str = "0.52",
    spread: str = "0.02",
    mid_price: str = "0.51",
    source: str = "test_regular_orderbook",
    seconds_old: int = 5,
    stale: bool = False,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    ts = now - timedelta(seconds=seconds_old)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        row = conn.execute(
            """
            INSERT INTO orderbook_snapshots (
                orderbook_snapshot_id, market_id, token_id, side, best_bid, best_ask,
                spread, mid_price, liquidity_score, source, snapshot_status,
                is_stale, snapshot_at, collected_at, created_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0.8,%s,'OK',%s,%s,%s,%s)
            RETURNING *, EXTRACT(EPOCH FROM (now() - COALESCE(snapshot_at, collected_at, created_at))) AS age_seconds
            """,
            (snapshot_ref, market_id, token_id, side, best_bid, best_ask, spread, mid_price, source, stale, ts, ts, now),
        ).fetchone()
        return dict(row)


def seed_intent(
    *,
    intent_id: str | None = None,
    market_id: str = "price-market",
    token_id: str = "price-token-yes",
    side: str = "YES",
    snapshot_id: int | None = None,
    intended_price: str = "0.55",
    quantity: str = "10",
) -> str:
    intent_id = intent_id or f"paper-intent-{uuid4().hex}"
    evidence = {
        "quantity": quantity,
        "paper_runtime_decision_id": f"decision-{intent_id}",
        "paper_runtime_decision": {
            "decision_id": f"decision-{intent_id}",
            "source_review_id": f"review-{intent_id}",
            "condition_id": f"condition-{market_id}",
            "token_id": token_id,
            "paper_enter_allowed": True,
            "blockers_json": [],
        },
        "paper_mode_policy": {"paper_enter_allowed": True, "blockers": []},
    }
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, orderbook_snapshot_id,
                intended_price, max_slippage, confidence, intent_status,
                intent_type, intent_reason, evidence, blockers, paper_only, live,
                execution_allowed, order_intent_created, generated_by, producer_name,
                is_runtime_generated, is_dry_run_generated, paper_session_id, created_at, updated_at
            )
            VALUES (
                %s,%s,'thesis','risk','exit',%s,%s,'ORDERBOOK_BEST_ASK',%s,
                %s,0.05,0.8,'CREATED','PAPER_ENTRY_INTENT','test price intent',
                %s,'[]'::jsonb,true,false,false,false,'test','paper_execution_test',
                true,false,'paper-execution-price-session',%s,%s
            )
            """,
            (
                intent_id,
                f"eligibility-{intent_id}",
                market_id,
                side,
                snapshot_id,
                intended_price,
                Jsonb(evidence),
                now,
                now,
            ),
        )
    return intent_id


def table_exists(conn: Any, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
