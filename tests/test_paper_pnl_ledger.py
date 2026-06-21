from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from test_paper_exit_loop import _lock_position, _prepare, _seed_position, _service


def test_daily_pnl_updates_after_close(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)

    _service().run_exit_loop(correlation_id="daily-pnl")

    with DatabaseConnectionFactory().connect() as conn:
        row = conn.execute("SELECT * FROM paper_daily_pnl").fetchone()
    assert float(row["realized_pnl"]) == 1.0
    assert float(row["net_pnl"]) == 1.0
    assert row["closed_trades_count"] == 1
    assert row["winning_trades_count"] == 1


def test_trade_ledger_writes_close_row_and_no_orphan_closed_position(postgres_test_schema) -> None:
    _prepare()
    position_id = _seed_position(mark=0.60, target=0.55)
    _lock_position(position_id)

    _service().run_exit_loop(correlation_id="ledger")

    with DatabaseConnectionFactory().connect() as conn:
        ledger = conn.execute("SELECT * FROM paper_trade_ledger WHERE event_type='CLOSE'").fetchone()
        orphan = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM paper_positions pp
            WHERE pp.current_status = 'CLOSED'
              AND NOT EXISTS (SELECT 1 FROM paper_position_closes ppc WHERE ppc.position_id = pp.id)
            """
        ).fetchone()["count"]
    assert ledger["event_type"] == "CLOSE"
    assert float(ledger["realized_pnl"]) == 1.0
    assert orphan == 0


def test_no_fake_pnl_when_no_paper_positions_exist(postgres_test_schema) -> None:
    _prepare()

    result = _service().run_exit_loop(correlation_id="none")

    assert result["status"] == "NO_OPEN_PAPER_POSITIONS"
    assert result["closed_positions_count"] == 0
    assert result["realized_pnl"] == 0
    with DatabaseConnectionFactory().connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS count FROM paper_position_closes").fetchone()["count"] == 0
