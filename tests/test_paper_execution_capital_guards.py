from __future__ import annotations

from uuid import uuid4
from decimal import Decimal

from psycopg.types.json import Jsonb

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_execution import PaperExecutionService
from app.services.paper_capital import PaperCapitalService
from test_paper_execution_service import _Governor, _Power, _prepare, _seed_intent


def _set_limits(**kwargs) -> None:
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        assignments = ", ".join(f"{key} = %s" for key in kwargs)
        conn.execute(f"UPDATE paper_accounts SET {assignments}, updated_at=now() WHERE account_id='paper_default'", tuple(kwargs.values()))


def _service() -> PaperExecutionService:
    power = _Power(True)
    return PaperExecutionService(system_power=power, governor=_Governor(True), paper_capital=PaperCapitalService(system_power=power))


def test_valid_paper_execution_locks_capital(postgres_test_schema) -> None:
    _prepare()
    _set_limits(risk_per_trade_pct=Decimal("10"))
    _seed_intent(quantity=10, best_ask=0.52)

    result = _service().run_execution(correlation_id="capital-lock")

    assert result["status"] == "OK"
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        ledger = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='CAPITAL_LOCKED_ON_FILL'").fetchone()
    assert account["available_balance"] == Decimal("994.80000000")
    assert account["locked_balance"] == Decimal("5.20000000")
    assert ledger["paper_fill_id"] is not None


def test_insufficient_balance_blocks_paper_execution(postgres_test_schema) -> None:
    _prepare()
    _set_limits(available_balance=Decimal("1"), risk_per_trade_pct=Decimal("100"), max_position_size=Decimal("100"))
    _seed_intent(quantity=10, best_ask=0.52)

    result = _service().run_execution(correlation_id="insufficient")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["INSUFFICIENT_PAPER_BALANCE"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0


def test_risk_per_trade_blocks_paper_execution(postgres_test_schema) -> None:
    _prepare()
    _set_limits(risk_per_trade_pct=Decimal("0.1"), max_position_size=Decimal("100"))
    _seed_intent(quantity=10, best_ask=0.52)

    result = _service().run_execution(correlation_id="risk-limit")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["RISK_PER_TRADE_LIMIT"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_fills") == 0


def test_risk_limit_clamps_paper_quantity_when_allowed_notional_is_meaningful(postgres_test_schema) -> None:
    _prepare()
    _set_limits(
        current_balance=Decimal("990"),
        available_balance=Decimal("990"),
        locked_balance=Decimal("0"),
        open_exposure=Decimal("0"),
        risk_per_trade_pct=Decimal("15"),
        max_position_size=Decimal("150"),
        max_total_open_exposure_pct=Decimal("80"),
        max_open_positions=3,
    )
    _seed_intent(quantity=300, best_ask=0.52, intended_price=0.55)

    result = _service().run_execution(correlation_id="risk-clamp")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        fill = conn.execute("SELECT * FROM paper_fills LIMIT 1").fetchone()
        order = conn.execute("SELECT * FROM paper_orders LIMIT 1").fetchone()
        metadata = dict(fill["metadata_json"])
    assert fill["quantity"] < Decimal("300")
    assert order["notional"] <= Decimal("148.5")
    assert metadata["risk_capital_clamped"] is True
    assert metadata["risk_capital_clamp_reason"] == "RISK_CAPITAL_SIZE_CLAMP"
    assert "RISK_PER_TRADE_LIMIT" in metadata["risk_capital_original_blockers"]


def test_daily_loss_guard_uses_active_paper_session_scope(postgres_test_schema) -> None:
    _prepare()
    position_id = uuid4()
    run_id = uuid4()
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute("DELETE FROM paper_sessions")
        conn.execute(
            """
            INSERT INTO paper_sessions (paper_session_id, session_name, starting_balance, current_balance_snapshot, status, created_by)
            VALUES
                ('old-session','Old Session',1000,900,'ARCHIVED','test'),
                ('active-session','Active Session',1000,1000,'ACTIVE','test')
            """
        )
        conn.execute(
            """
            INSERT INTO paper_runs (
                id, mode, started_at, ended_at, status, markets_seen_count,
                markets_ranked_count, candidates_selected_count, signals_emitted_count,
                metadata_json
            )
            VALUES (%s,'PAPER_SIM',now(),now(),'COMPLETED',1,1,1,1,%s)
            """,
            (run_id, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO paper_positions (
                id, paper_run_id, market_id, intended_outcome, size, avg_entry, mark_price,
                unrealized, realized, current_status, thesis_state, invalidation_state,
                opened_at, updated_at, closed_at, payload_json
            )
            VALUES (%s,%s,'old-market','YES',10,0.5,0.4,0,-100,'CLOSED','CLOSED','NONE',now(),now(),now(),%s)
            """,
            (position_id, run_id, Jsonb({})),
        )
        conn.execute(
            """
            INSERT INTO paper_position_closes (
                close_id, position_id, market_id, side, entry_price, exit_price,
                quantity, realized_pnl, realized_pnl_pct, exit_reason, price_basis,
                source_exit_price, metadata_json, paper_session_id, created_at
            )
            VALUES ('old-close',%s,'old-market','YES',0.5,0.4,10,-100,-20,'MANUAL_PAPER_CLOSE','TEST','TEST',%s,'old-session',now())
            """,
            (position_id, Jsonb({})),
        )
        _set_limits(
            current_balance=Decimal("1000"),
            available_balance=Decimal("1000"),
            risk_per_trade_pct=Decimal("15"),
            max_position_size=Decimal("150"),
            max_daily_loss_pct=Decimal("5"),
        )
        check = PaperCapitalService(system_power=_Power(True)).precheck_fill(
            conn,
            paper_intent_id="intent-active-session",
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
            write_block=False,
        )

    assert "DAILY_LOSS_LIMIT" not in check.blockers
    assert check.allowed is True


def test_max_open_positions_blocks_paper_execution(postgres_test_schema) -> None:
    _prepare()
    _set_limits(risk_per_trade_pct=Decimal("100"), max_open_positions=0)
    _seed_intent(quantity=10, best_ask=0.52)

    result = _service().run_execution(correlation_id="max-open")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["MAX_OPEN_POSITIONS"] == 1


def test_max_exposure_blocks_paper_execution(postgres_test_schema) -> None:
    _prepare()
    _set_limits(risk_per_trade_pct=Decimal("100"), max_position_size=Decimal("100"), max_total_open_exposure_pct=Decimal("0.1"))
    _seed_intent(quantity=10, best_ask=0.52)

    result = _service().run_execution(correlation_id="max-exposure")

    assert result["status"] == "NO_VALID_PAPER_INTENTS"
    assert result["block_reasons_json"]["MAX_EXPOSURE_LIMIT"] == 1


def test_lock_failure_rolls_back_position_and_keeps_capital_reconciled(postgres_test_schema) -> None:
    _prepare()
    _set_limits(risk_per_trade_pct=Decimal("100"), max_open_positions=3)
    for idx in range(4):
        _seed_intent(market_id=f"paper-exec-market-{idx}", quantity=10, best_ask=0.52, intended_price=0.55)

    result = _service().run_execution(correlation_id="max-open-partial")

    assert result["status"] == "DEGRADED"
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 3
        assert _count(conn, "paper_fills") == 3
        assert _count(conn, "paper_positions") == 3
        locks = conn.execute("SELECT COUNT(*) AS count FROM paper_capital_ledger WHERE event_type='CAPITAL_LOCKED_ON_FILL'").fetchone()
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        reconciliation = PaperCapitalService().reconcile(conn=conn)
    assert locks["count"] == 3
    assert account["locked_balance"] == Decimal("15.60000000")
    assert account["open_exposure"] == Decimal("15.60000000")
    assert reconciliation["capital_reconciliation_status"] == "OK"


def _count(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
