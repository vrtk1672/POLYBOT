from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_capital import PaperCapitalService


class _Power:
    def __init__(self, on: bool = True) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_capital_ledger",
            "paper_accounts",
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
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(
            """
            INSERT INTO paper_accounts (
                account_id, name, currency, initial_balance, current_balance,
                available_balance, locked_balance, open_exposure, risk_per_trade_pct,
                max_position_size, max_daily_loss_pct, max_open_positions,
                max_total_open_exposure_pct, status
            )
            VALUES ('paper_default', 'Default Paper Account', 'USD', 1000, 1000, 1000, 0, 0, 1, 25, 5, 3, 15, 'ACTIVE')
            """
        )


def test_default_paper_account_schema_exists(postgres_test_schema) -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
    assert account["initial_balance"] == Decimal("1000.00000000")
    assert account["currency"] == "USD"


def test_fill_locks_capital_and_reconciliation_ok(postgres_test_schema) -> None:
    _prepare()
    service = PaperCapitalService(system_power=_Power(True))
    position_id = str(uuid4())
    run_id = str(uuid4())
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count
            )
            VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                current_status, thesis_state, invalidation_state, opened_at, payload_json
            )
            VALUES (%s, %s, 'm1', 'YES', 10, 0.50, 'OPEN', 'ACTIVE', 'NONE', now(), '{}'::jsonb)
            """,
            (position_id, run_id),
        )
        result = service.lock_on_fill(
            conn,
            paper_intent_id="intent-1",
            paper_order_id=str(uuid4()),
            paper_fill_id="fill-1",
            paper_position_id=position_id,
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
        )
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        reconciliation = service.reconcile(conn=conn)

    assert result["status"] == "LOCKED"
    assert account["available_balance"] == Decimal("995.00000000")
    assert account["locked_balance"] == Decimal("5.00000000")
    assert account["open_exposure"] == Decimal("5.00000000")
    assert reconciliation["capital_reconciliation_status"] == "OK"


def test_system_off_blocks_capital_lock(postgres_test_schema) -> None:
    _prepare()
    service = PaperCapitalService(system_power=_Power(False))
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        try:
            service.lock_on_fill(
                conn,
                paper_intent_id="intent-off",
                paper_order_id=str(uuid4()),
                paper_fill_id="fill-off",
                paper_position_id=str(uuid4()),
                fill_price=Decimal("0.50"),
                quantity=Decimal("10"),
            )
        except RuntimeError as exc:
            assert "SYSTEM_POWER_OFF" in str(exc)
        else:
            raise AssertionError("SYSTEM OFF did not block capital lock")
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
    assert account["available_balance"] == Decimal("1000.00000000")


def test_quarantined_positions_excluded_from_capital_reconciliation(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        run_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count
            )
            VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                current_status, thesis_state, invalidation_state, opened_at,
                excluded_from_active_paper_truth, payload_json
            )
            VALUES (%s, %s, 'm1', 'YES', 100, 0.50, 'QUARANTINED', 'ACTIVE', 'NONE', now(), true, '{}'::jsonb)
            """,
            (str(uuid4()), run_id),
        )
        result = PaperCapitalService(system_power=_Power(True)).reconcile(conn=conn)
    assert result["capital_reconciliation_status"] == "OK"


def test_open_position_without_capital_lock_returns_red(postgres_test_schema) -> None:
    _prepare()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        run_id = str(uuid4())
        position_id = str(uuid4())
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count
            )
            VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                current_status, thesis_state, invalidation_state, opened_at, payload_json
            )
            VALUES (%s, %s, 'm1', 'YES', 10, 0.50, 'OPEN', 'ACTIVE', 'NONE', now(), '{}'::jsonb)
            """,
            (position_id, run_id),
        )
        result = PaperCapitalService(system_power=_Power(True)).reconcile(conn=conn)

    assert result["capital_reconciliation_status"] == "RED"
    assert "OPEN_POSITION_WITHOUT_ACTIVE_LOCK" in result["reconciliation_errors"]
    assert result["expected_locked_balance"] == 0.0
    assert result["expected_open_exposure"] == 5.0
    assert result["open_positions_without_lock"][0]["paper_position_id"] == position_id


def test_legitimate_backfill_from_real_fill_creates_audit_lock(postgres_test_schema) -> None:
    _prepare()
    run_id = str(uuid4())
    signal_id = str(uuid4())
    order_id = str(uuid4())
    position_id = str(uuid4())
    fill_id = f"fill-{position_id}"
    intent_id = f"intent-{position_id}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count
            )
            VALUES (%s, 'PAPER_SIM', now(), now(), 'COMPLETED', 1, 1, 1, 1)
            """,
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO paper_intents (
                paper_intent_id, eligibility_id, thesis_id, risk_decision_id,
                exit_plan_id, market_id, side, price_basis, intended_price,
                intent_status, intent_type, intent_reason, evidence, blockers,
                paper_only, live, execution_allowed, order_intent_created,
                generated_by, producer_name, is_runtime_generated, is_dry_run_generated
            )
            VALUES (
                %s, %s, 'thesis-test', 'risk-test', 'exit-test',
                'm1', 'YES', 'ORDERBOOK_BEST_ASK', 0.50,
                'POSITION_OPENED', 'PAPER_ENTRY_INTENT', 'test backfill intent', %s, '[]'::jsonb,
                true, false, false, false, 'test', 'paper_capital_test', true, false
            )
            """,
            (intent_id, f"eligibility-{position_id}", Jsonb({"quantity": 10})),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, intended_price, intended_size,
                guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, 'm1', 'WOULD_ENTER', 'YES', 'PAPER_ENTRY', 'test', 0.50, 10, 'PASS', 'test', 'test', '{}'::jsonb)
            """,
            (signal_id, run_id),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, avg_fill_price,
                min_size_check_passed, payload_json
            )
            VALUES (%s, %s, %s, 'm1', 'YES', 'BUY', 0.50, 10, 5, 'FILLED', 1, 10, 0, 0.50, true, %s)
            """,
            (order_id, run_id, signal_id, Jsonb({"source_intent_id": intent_id})),
        )
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id,
                side, fill_price, quantity, price_basis, metadata_json
            )
            VALUES (%s, %s, %s, 'm1', 'YES', 0.50, 10, 'TEST_FILL', '{}'::jsonb)
            """,
            (fill_id, order_id, intent_id),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                current_status, thesis_state, invalidation_state, opened_at, payload_json
            )
            VALUES (%s, %s, 'm1', 'YES', 10, 0.50, 'OPEN', 'ACTIVE', 'NONE', now(), %s)
            """,
            (position_id, run_id, Jsonb({"source_intent_id": intent_id, "paper_order_id": order_id, "paper_fill_id": fill_id})),
        )

    result = PaperCapitalService(system_power=_Power(False)).backfill_missing_open_position_locks_from_real_fills(actor="test")

    assert result["status"] == "OK"
    assert result["backfilled"] == 1
    assert result["reconciliation"]["capital_reconciliation_status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        ledger = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='CAPITAL_LOCK_BACKFILLED_FROM_REAL_FILL'").fetchone()
    assert account["available_balance"] == Decimal("995.00000000")
    assert account["locked_balance"] == Decimal("5.00000000")
    assert ledger["paper_position_id"] == position_id
    assert ledger["metadata_json"]["repair"] is True


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
