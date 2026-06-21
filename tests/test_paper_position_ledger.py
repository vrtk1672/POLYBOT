from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.services.paper_exit_loop import PaperExitLoopService

from test_paper_execution_service import _prepare, _seed_intent, _service


def test_valid_fill_opens_position_and_open_ledger(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    result = _service().run_execution(correlation_id="ledger")

    assert result["positions_created"] == 1
    with DatabaseConnectionFactory().connect() as conn:
        position = conn.execute("SELECT * FROM paper_positions").fetchone()
        ledger = conn.execute("SELECT * FROM paper_trade_ledger WHERE event_type='OPEN'").fetchone()
    assert position["current_status"] == "OPEN"
    assert ledger["position_id"] == position["id"]
    assert ledger["reason"] == "PAPER_POSITION_OPENED"


def test_paper_exit_loop_can_see_open_position(postgres_test_schema) -> None:
    _prepare()
    _seed_intent(best_ask=0.52)
    _service().run_execution(correlation_id="open-for-exit")

    summary = PaperExitLoopService().get_exits_dashboard_summary()

    assert summary["open_paper_positions"] == 1
    assert summary["pending_exit_checks"] == 1
