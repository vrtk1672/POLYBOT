from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.services.paper_capital import PaperCapitalService
from app.services.paper_exit_loop import PaperExitLoopService


class _Power:
    def __init__(self, on: bool) -> None:
        self.on = on

    def get_power_state(self) -> dict[str, object]:
        return {"power": "ON" if self.on else "OFF", "runtime_work_allowed": self.on}


class _Governor:
    def __init__(self, allow: bool = True) -> None:
        self.allow = allow

    def can_execute(self, action) -> bool:
        return self.allow


def _prepare() -> None:
    run_migrations()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for table in (
            "paper_exit_loop_runs",
            "paper_trade_ledger",
            "paper_position_closes",
            "paper_daily_pnl",
            "paper_fills",
            "paper_position_events",
            "paper_positions",
            "paper_orders",
            "paper_signals",
            "paper_runs",
            "paper_intents",
            "exit_plans",
            "orderbook_snapshots",
        ):
            if _table_exists(conn, table):
                conn.execute(f"DELETE FROM {table}")


def _seed_position(
    *,
    market_id: str = "paper-exit-market",
    side: str = "YES",
    entry: float = 0.50,
    mark: float | None = 0.60,
    target: float = 0.55,
    stop: float = 0.45,
    max_hold_seconds: int = 3600,
    opened_delta: timedelta = timedelta(minutes=5),
) -> str:
    paper_run_id = str(uuid4())
    signal_id = str(uuid4())
    order_id = str(uuid4())
    position_id = str(uuid4())
    intent_id = f"paper-intent-{position_id}"
    fill_id = f"paper-fill-{position_id}"
    now = datetime.now(UTC)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
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
                %s, %s, 'ORDERBOOK_BEST_ASK', %s,
                'POSITION_OPENED', 'PAPER_ENTRY_INTENT', 'test position intent', %s, '[]'::jsonb,
                true, false, false, false, 'test', 'paper_exit_test', true, false
            )
            """,
            (intent_id, f"eligibility-{position_id}", market_id, side, entry, Jsonb({"quantity": 10})),
        )
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, cycle_id, mode, started_at, ended_at, status,
                markets_seen_count, markets_ranked_count, candidates_selected_count,
                signals_emitted_count, metadata_json
            )
            VALUES (%s, NULL, 'EXECUTION_AWARE_PAPER', %s, %s, 'COMPLETED', 1, 1, 1, 1, '{}'::jsonb)
            """,
            (paper_run_id, now, now),
        )
        conn.execute(
            """
            INSERT INTO paper_signals (
                id, paper_run_id, market_id, signal_type, intended_outcome,
                trade_type, bucket_type, intended_price, intended_size,
                guard_result, reason_code, reason_text, payload_json
            )
            VALUES (%s, %s, %s, 'WOULD_ENTER', %s, 'PAPER_ENTRY', 'test', %s, 10, 'PASS', 'test', 'test', %s)
            """,
            (signal_id, paper_run_id, market_id, side, entry, Jsonb({"source_intent_id": intent_id})),
        )
        conn.execute(
            """
            INSERT INTO paper_orders (
                id, paper_run_id, paper_signal_id, market_id, intended_outcome,
                action, intended_price, intended_size, notional, status,
                fill_ratio, filled_size, remaining_size, avg_fill_price,
                min_size_check_passed, payload_json
            )
            VALUES (%s, %s, %s, %s, %s, 'BUY', %s, 10, %s, 'FILLED', 1, 10, 0, %s, true, %s)
            """,
            (order_id, paper_run_id, signal_id, market_id, side, entry, entry * 10, entry, Jsonb({"source_intent_id": intent_id})),
        )
        conn.execute(
            """
            INSERT INTO paper_fills (
                paper_fill_id, paper_order_id, source_intent_id, market_id,
                side, fill_price, quantity, price_basis, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, 10, 'TEST_FILL', '{}'::jsonb)
            """,
            (fill_id, order_id, intent_id, market_id, side, entry),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry,
                mark_price, unrealized, realized, current_status, thesis_state,
                invalidation_state, opened_at, updated_at, closed_at, payload_json
            )
            VALUES (%s, %s, %s, %s, 10, %s, %s, 0, 0, 'OPEN', 'ACTIVE', 'NONE', %s, %s, NULL, %s)
            """,
            (
                position_id,
                paper_run_id,
                market_id,
                side,
                entry,
                entry,
                now - opened_delta,
                now,
                Jsonb({"source_intent_id": intent_id, "paper_order_id": order_id, "paper_fill_id": fill_id}),
            ),
        )
        conn.execute(
            """
            INSERT INTO paper_trade_ledger (
                ledger_id, position_id, event_type, market_id, side, amount,
                unrealized_pnl, reason, metadata_json
            )
            VALUES (%s, %s, 'OPEN', %s, %s, %s, 0, 'TEST_OPEN', '{}'::jsonb)
            """,
            (f"paper_open_{position_id}", position_id, market_id, side, entry * 10),
        )
        if mark is not None:
            conn.execute(
                """
                INSERT INTO orderbook_snapshots (
                    orderbook_snapshot_id, market_id, side, best_bid, best_ask,
                    spread, mid_price, liquidity_score, source, snapshot_status,
                    is_stale, collected_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, 0.02, %s, 0.8, 'test', 'OK', false, now(), now())
                """,
                (f"book-{position_id}", market_id, side, mark - 0.01, mark + 0.01, mark),
            )
        conn.execute(
            """
            INSERT INTO exit_plans (
                exit_plan_id, market_id, side, plan_status, created_from,
                target_exit, stop_loss, max_hold_seconds, status, exit_type,
                paper_exit_ready, risk_decision_ref, invalidation_rules,
                emergency_exit_rules, liquidity_exit_check, time_exit_check,
                missing_exit_evidence, blockers, warnings
            )
            VALUES (
                %s, %s, %s, 'READY', 'exit_foundation',
                %s, %s, %s, 'COMPLETE', 'BASIC_PROTECTIVE_EXIT',
                true, 'risk-test', '[]'::jsonb, '[]'::jsonb, '{}'::jsonb,
                '{}'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb
            )
            """,
            (f"exit-{position_id}", market_id, side, target, stop, max_hold_seconds),
        )
    return position_id


def _service(on: bool = True, allow: bool = True) -> PaperExitLoopService:
    return PaperExitLoopService(system_power=_Power(on), governor=_Governor(allow))


def _lock_position(position_id: str) -> None:
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        capital.lock_on_fill(
            conn,
            paper_intent_id=position["payload_json"]["source_intent_id"],
            paper_order_id=position["payload_json"]["paper_order_id"],
            paper_fill_id=position["payload_json"]["paper_fill_id"],
            paper_position_id=position_id,
            fill_price=position["avg_entry"],
            quantity=position["size"],
        )


def test_close_open_paper_position_at_take_profit(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)

    result = _service().run_exit_loop(correlation_id="take-profit")

    assert result["status"] == "OK"
    assert result["closed_positions_count"] == 1
    assert result["realized_pnl"] == 1.0
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        close = conn.execute("SELECT * FROM paper_position_closes WHERE position_id=%s", (position_id,)).fetchone()
    assert position["current_status"] == "CLOSED"
    assert close["exit_reason"] == "TAKE_PROFIT"
    assert float(close["realized_pnl"]) == 1.0


def test_close_open_paper_position_at_stop_loss(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.40, target=0.90, stop=0.45)
    _lock_position(position_id)

    result = _service().run_exit_loop(correlation_id="stop-loss")

    assert result["closed_positions_count"] == 1
    assert result["realized_pnl"] == -1.0
    with DatabaseConnectionFactory().connect() as conn:
        close = conn.execute("SELECT * FROM paper_position_closes").fetchone()
    assert close["exit_reason"] == "STOP_LOSS"


def test_close_open_paper_position_at_max_hold_time(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.51, target=0.90, stop=0.10, max_hold_seconds=1, opened_delta=timedelta(minutes=2))
    _lock_position(position_id)

    result = _service().run_exit_loop(correlation_id="max-hold")

    assert result["closed_positions_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        close = conn.execute("SELECT * FROM paper_position_closes").fetchone()
    assert close["exit_reason"] == "MAX_HOLD_TIME"


def test_does_not_close_without_exit_condition(postgres_test_schema) -> None:
    _prepare()
    _seed_position(mark=0.51, target=0.90, stop=0.10, max_hold_seconds=3600)

    result = _service().run_exit_loop(correlation_id="hold")

    assert result["closed_positions_count"] == 0
    assert result["marked_positions_count"] == 1
    assert result["no_exit_condition_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT * FROM paper_positions").fetchone()
    assert position["current_status"] == "OPEN"
    assert float(position["unrealized"]) == 0.1


def test_does_not_close_without_exit_price(postgres_test_schema) -> None:
    _prepare()
    _seed_position(mark=None)

    result = _service().run_exit_loop(correlation_id="missing-price")

    assert result["closed_positions_count"] == 0
    assert result["no_exit_price_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_position_closes").fetchone()["count"] == 0


def test_no_duplicate_close_on_repeated_runs(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)

    first = _service().run_exit_loop(correlation_id="first")
    second = _service().run_exit_loop(correlation_id="second")

    assert first["closed_positions_count"] == 1
    assert second["status"] == "OK" or second["status"] == "NO_OPEN_PAPER_POSITIONS"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_position_closes").fetchone()["count"] == 1


def test_system_off_blocks_paper_exit_loop(postgres_test_schema) -> None:
    _prepare()
    _seed_position(mark=0.60, target=0.55)

    result = _service(on=False).run_exit_loop(correlation_id="off")

    assert result["status"] == "BLOCKED"
    assert result["blocked_reason"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_position_closes").fetchone()["count"] == 0


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()["table_name"])
