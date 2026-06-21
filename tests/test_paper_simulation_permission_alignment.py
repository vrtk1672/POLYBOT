from __future__ import annotations

from app.db.migrate import run_migrations
from app.runtime.modes import RuntimeAction, RuntimeMode, get_permissions_for_mode
from app.runtime.state_governor import StateGovernor
from app.services.system_power import SystemPowerService


def test_data_only_allows_safe_paper_simulation_but_not_paper_engine_or_live() -> None:
    permissions = get_permissions_for_mode(RuntimeMode.DATA_ONLY)

    assert permissions.allows(RuntimeAction.RUN_PAPER_SIMULATION)
    assert not permissions.allows(RuntimeAction.RUN_PAPER_ENGINE)
    assert not permissions.allows(RuntimeAction.OPEN_PAPER_POSITION)
    assert not permissions.allows(RuntimeAction.CREATE_ORDER_INTENT, {"paper": True})
    assert not permissions.allows(RuntimeAction.OPEN_SHADOW_POSITION)
    assert not permissions.allows(RuntimeAction.SEND_LIVE_ORDER)


def test_system_off_blocks_safe_paper_simulation(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_off(actor="test", reason="paper_simulation_permission_off")

    governor = StateGovernor()

    assert not governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION)
    assert not governor.can_execute(RuntimeAction.RUN_PAPER_ENGINE)
    assert not governor.can_execute(RuntimeAction.OPEN_PAPER_POSITION)


def test_system_power_dashboard_separates_simulation_from_legacy_paper_engine(postgres_test_schema) -> None:
    run_migrations()
    SystemPowerService().turn_on(actor="test", reason="paper_simulation_permission_on")

    payload = SystemPowerService().get_dashboard_summary()

    assert payload["mock_data"] is False
    assert payload["runtime_work_allowed"] is True
    assert payload["paper_simulation_allowed"] is True
    assert payload["paper_execution_allowed"] is True
    assert payload["paper_allowed"] is False
    assert payload["shadow_allowed"] is False
    assert payload["live_allowed"] is False
    assert payload["safety"]["execution_allowed"] is False
