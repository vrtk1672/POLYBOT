from __future__ import annotations

import pytest

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.runtime_errors import RuntimeModeTransitionDenied, RuntimePermissionDenied
from app.runtime.state_governor import StateGovernor


def _governor(postgres_test_schema) -> StateGovernor:
    run_migrations()
    return StateGovernor(connection_factory=DatabaseConnectionFactory())


def test_initial_state_defaults_to_data_only(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    state = governor.ensure_initial_state()
    assert state.current_mode == RuntimeMode.DATA_ONLY


def test_mode_change_writes_history(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    governor.request_mode_change(RuntimeMode.PAPER, actor="operator", reason="paper validation")
    with DatabaseConnectionFactory().connect() as conn:
        history = RuntimeStateRepository().list_history(conn, 10)
    assert any(row["to_mode"] == "PAPER" and row["allowed"] is True for row in history)


def test_blocked_mode_change_writes_history(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    with pytest.raises(RuntimeModeTransitionDenied):
        governor.request_mode_change(RuntimeMode.SMALL_LIVE, actor="operator", reason="too soon")
    with DatabaseConnectionFactory().connect() as conn:
        history = RuntimeStateRepository().list_history(conn, 10)
    assert any(row["to_mode"] == "SMALL_LIVE" and row["allowed"] is False for row in history)


def test_activate_kill_sets_kill_and_switch(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    state = governor.activate_kill(actor="operator", reason="manual emergency")
    assert state.current_mode == RuntimeMode.KILL
    assert state.kill_switch_active is True


def test_resume_from_kill_defaults_to_data_only(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    governor.activate_kill(actor="operator", reason="manual emergency")
    state = governor.resume_from_kill(actor="operator", reason="investigated")
    assert state.current_mode == RuntimeMode.DATA_ONLY
    assert state.kill_switch_active is False


def test_can_execute_respects_current_mode(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    assert governor.can_execute(RuntimeAction.COLLECT_DATA)
    assert not governor.can_execute(RuntimeAction.OPEN_PAPER_POSITION)
    governor.request_mode_change(RuntimeMode.PAPER, actor="operator", reason="paper validation")
    assert governor.can_execute(RuntimeAction.OPEN_PAPER_POSITION)


def test_assert_can_execute_raises_permission_denied(postgres_test_schema) -> None:
    governor = _governor(postgres_test_schema)
    governor.ensure_initial_state()
    with pytest.raises(RuntimePermissionDenied):
        governor.assert_can_execute(RuntimeAction.SEND_LIVE_ORDER)
