from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from test_paper_execution_service import _count, _prepare, _seed_intent, _service
from test_paper_exit_loop import _prepare as _prepare_exit
from test_paper_exit_loop import _seed_position, _service as _exit_service


def test_system_off_blocks_runtime_paper_activity(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    result = _service(on=False).run_execution(correlation_id="runtime-off")

    assert result["status"] == "SYSTEM_POWER_OFF"
    with DatabaseConnectionFactory().connect() as conn:
        assert _count(conn, "paper_orders") == 0
        assert _count(conn, "paper_fills") == 0
        assert _count(conn, "paper_positions") == 0


def test_system_on_runs_paper_safe_runtime_from_valid_intent(postgres_test_schema) -> None:
    _prepare()
    _seed_intent()

    result = _service(on=True, allow=True).run_execution(correlation_id="runtime-on")

    assert result["status"] == "OK"
    assert result["orders_created"] == 1
    assert result["fills_created"] == 1
    assert result["positions_created"] == 1


def test_paper_exit_loop_observes_open_positions_without_forced_close(postgres_test_schema) -> None:
    _prepare_exit()
    _seed_position(mark=0.51, target=0.90, stop=0.10, max_hold_seconds=3600)

    result = _exit_service().run_exit_loop(correlation_id="hold-open-position")

    assert result["status"] == "OK"
    assert result["open_positions_checked"] == 1
    assert result["closed_positions_count"] == 0
    assert result["no_exit_condition_count"] == 1
