from __future__ import annotations

from decimal import Decimal

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_capital import PaperCapitalService
from app.services.paper_exit_loop import PaperExitLoopService
from test_paper_exit_loop import _Governor, _Power, _prepare, _seed_position


def test_close_releases_capital_and_applies_realized_pnl(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
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
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
        )

    result = PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="release")

    assert result["closed_positions_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        release = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='CAPITAL_RELEASED_ON_CLOSE'").fetchone()
        realized = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='REALIZED_PNL_APPLIED'").fetchone()
    assert account["current_balance"] == Decimal("1001.00000000")
    assert account["available_balance"] == Decimal("1001.00000000")
    assert account["locked_balance"] == Decimal("0E-8")
    assert release is not None
    assert realized["realized_pnl_delta"] == Decimal("1.00000000")


def test_duplicate_close_does_not_double_release(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
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
            fill_price=Decimal("0.50"),
            quantity=Decimal("10"),
        )
    service = PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital)
    first = service.run_exit_loop(correlation_id="release-1")
    second = service.run_exit_loop(correlation_id="release-2")

    assert first["closed_positions_count"] == 1
    assert second["status"] == "NO_OPEN_PAPER_POSITIONS"
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        releases = conn.execute("SELECT COUNT(*) AS count FROM paper_capital_ledger WHERE event_type='CAPITAL_RELEASED_ON_CLOSE'").fetchone()
    assert account["current_balance"] == Decimal("1001.00000000")
    assert releases["count"] == 1


def test_three_opens_two_closes_one_position_remains_locked(postgres_test_schema) -> None:
    _prepare()
    close_one = _seed_position(market_id="partial-1", mark=0.60, target=0.55, entry=0.50)
    close_two = _seed_position(market_id="partial-2", mark=0.60, target=0.55, entry=0.50)
    hold_one = _seed_position(market_id="partial-3", mark=0.50, target=0.90, stop=0.10, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        for position_id in (close_one, close_two, hold_one):
            position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
            capital.lock_on_fill(
                conn,
                paper_intent_id=position["payload_json"]["source_intent_id"],
                paper_order_id=position["payload_json"]["paper_order_id"],
                paper_fill_id=position["payload_json"]["paper_fill_id"],
                paper_position_id=position_id,
                fill_price=Decimal("0.50"),
                quantity=Decimal("10"),
                skip_precheck=True,
            )

    result = PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="partial-release")

    assert result["closed_positions_count"] == 2
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        open_position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (hold_one,)).fetchone()
        releases = conn.execute("SELECT COUNT(*) AS count FROM paper_capital_ledger WHERE event_type='CAPITAL_RELEASED_ON_CLOSE'").fetchone()
        reconciliation = capital.reconcile(conn=conn)
    assert open_position["current_status"] == "OPEN"
    assert account["locked_balance"] == Decimal("5.00000000")
    assert account["open_exposure"] == Decimal("5.00000000")
    assert releases["count"] == 2
    assert reconciliation["capital_reconciliation_status"] == "OK"


def test_close_releases_backfilled_capital_lock(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    backfill = capital.backfill_missing_open_position_locks_from_real_fills(actor="test")

    assert backfill["backfilled"] == 1

    result = PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="release-backfill")

    assert result["closed_positions_count"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        release = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='CAPITAL_RELEASED_ON_CLOSE' AND paper_position_id=%s", (position_id,)).fetchone()
        realized = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='REALIZED_PNL_APPLIED' AND paper_position_id=%s", (position_id,)).fetchone()
        reconciliation = capital.reconcile(conn=conn)
    assert release is not None
    assert realized is not None
    assert account["locked_balance"] == Decimal("0E-8")
    assert account["open_exposure"] == Decimal("0E-8")
    assert reconciliation["capital_reconciliation_status"] == "OK"


def test_close_without_active_lock_rolls_back_close(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)

    result = PaperExitLoopService(system_power=power, governor=_Governor(True), paper_capital=capital).run_exit_loop(correlation_id="missing-lock")

    assert result["closed_positions_count"] == 0
    assert result["blocked_positions_count"] == 1
    assert "NO_CAPITAL_LOCK_FOUND" in result["error_summary"]
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT * FROM paper_positions WHERE id=%s", (position_id,)).fetchone()
        closes = conn.execute("SELECT COUNT(*) AS count FROM paper_position_closes WHERE position_id=%s", (position_id,)).fetchone()
        close_ledgers = conn.execute("SELECT COUNT(*) AS count FROM paper_trade_ledger WHERE position_id=%s AND event_type='CLOSE'", (position_id,)).fetchone()
    assert position["current_status"] == "OPEN"
    assert closes["count"] == 0
    assert close_ledgers["count"] == 0


def test_audited_backfill_from_real_close_releases_and_applies_pnl(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55, entry=0.50)
    power = _Power(True)
    capital = PaperCapitalService(system_power=power)
    capital.backfill_missing_open_position_locks_from_real_fills(actor="test")
    close_id = f"paper_close_{position_id}"
    with DatabaseConnectionFactory().connect() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO paper_position_closes (
                close_id, position_id, trade_id, market_id, side, entry_price,
                exit_price, quantity, realized_pnl, realized_pnl_pct, exit_reason,
                price_basis, source_exit_price, correlation_id, metadata_json, created_at
            )
            SELECT %s, id, paper_run_id, market_id, intended_outcome, avg_entry,
                   0.60, size, 1.00, 0.20, 'TAKE_PROFIT',
                   'TEST', 'test', 'repair-test', '{"paper_only": true}'::jsonb, now()
            FROM paper_positions
            WHERE id=%s
            """,
            (close_id, position_id),
        )
        conn.execute(
            """
            UPDATE paper_positions
            SET current_status='CLOSED', closed_at=now(), mark_price=0.60,
                unrealized=0, realized=1.00, updated_at=now()
            WHERE id=%s
            """,
            (position_id,),
        )

    repair = capital.backfill_missing_close_releases_from_real_closes(actor="test-repair")

    assert repair["backfilled"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        account = conn.execute("SELECT * FROM paper_accounts WHERE account_id='paper_default'").fetchone()
        release = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='CAPITAL_RELEASE_BACKFILLED_FROM_REAL_CLOSE' AND paper_close_id=%s", (close_id,)).fetchone()
        realized = conn.execute("SELECT * FROM paper_capital_ledger WHERE event_type='REALIZED_PNL_BACKFILLED_FROM_REAL_CLOSE' AND paper_close_id=%s", (close_id,)).fetchone()
        reconciliation = capital.reconcile(conn=conn)
    assert release is not None
    assert realized is not None
    assert realized["realized_pnl_delta"] == Decimal("1.00000000")
    assert account["current_balance"] == Decimal("1001.00000000")
    assert account["available_balance"] == Decimal("1001.00000000")
    assert account["locked_balance"] == Decimal("0E-8")
    assert reconciliation["capital_reconciliation_status"] == "OK"
