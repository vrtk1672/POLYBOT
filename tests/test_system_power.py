from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.db.migrate import run_migrations
from app.repositories.runtime_state_repository import SystemPowerRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService


def test_get_system_power_returns_current_state(postgres_test_schema) -> None:
    run_migrations()
    payload = SystemPowerService().get_power_state()

    assert payload["power"] == "ON"
    assert payload["runtime_work_allowed"] is True
    assert payload["safety"]["live_trading_enabled"] is False


def test_on_and_off_transitions_write_audit_records(postgres_test_schema) -> None:
    run_migrations()
    service = SystemPowerService()

    off = service.turn_off(actor="operator", reason="manual_system_off", correlation_id="power-test")
    on = service.turn_on(actor="operator", reason="manual_system_on", correlation_id="power-test-on")

    assert off["power"] == "OFF"
    assert on["power"] == "ON"
    with DatabaseConnectionFactory().connect() as conn:
        rows = SystemPowerRepository().list_transitions(conn, limit=10)
    assert any(row["new_power"] == "OFF" and row["actor"] == "operator" for row in rows)
    assert any(row["new_power"] == "ON" and row["actor"] == "operator" for row in rows)


def test_repeated_transitions_are_audited_safely(postgres_test_schema) -> None:
    run_migrations()
    service = SystemPowerService()

    first = service.turn_off(actor="operator", reason="manual_system_off")
    second = service.turn_off(actor="operator", reason="manual_system_off_again")

    assert first["power"] == "OFF"
    assert second["power"] == "OFF"
    with DatabaseConnectionFactory().connect() as conn:
        rows = SystemPowerRepository().list_transitions(conn, limit=10)
    assert len([row for row in rows if row["new_power"] == "OFF"]) == 2


def test_system_off_blocks_governor_permissions(postgres_test_schema) -> None:
    run_migrations()
    service = SystemPowerService()
    governor = StateGovernor()

    assert governor.can_execute(RuntimeAction.COLLECT_DATA)
    service.turn_off(actor="operator", reason="manual_system_off")

    assert not governor.can_execute(RuntimeAction.COLLECT_DATA)
    assert not governor.can_execute(RuntimeAction.RUN_PAPER_ENGINE)
    assert not governor.can_execute(RuntimeAction.RUN_SHADOW_ENGINE)
    assert not governor.can_execute(RuntimeAction.RUN_LIVE_ENGINE)
