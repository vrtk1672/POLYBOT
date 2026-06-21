from __future__ import annotations

from app.control_center.paper_simulation import PaperSimulationActionRequest, PaperSimulationControlService
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.system_power import SystemPower


class _Governor:
    def __init__(self, *, mode: RuntimeMode = RuntimeMode.DATA_ONLY, power: SystemPower = SystemPower.ON, kill: bool = False) -> None:
        self.state = RuntimeState(
            current_mode=mode,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=kill,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=power,
            metadata_json={},
        )
        self.actions: list[str] = []

    def get_current_state(self) -> RuntimeState:
        return self.state

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return self.state.system_power == SystemPower.ON and value in {
            RuntimeAction.COLLECT_DATA.value,
            RuntimeAction.RUN_PAPER_SIMULATION.value,
        }

    def request_mode_change(self, to_mode, *, actor: str, reason: str, metadata=None, correlation_id=None, action: str = "REQUEST_MODE_CHANGE") -> RuntimeState:
        self.actions.append(action)
        self.state = RuntimeState(
            current_mode=RuntimeMode(str(to_mode).strip().upper()),
            previous_mode=self.state.current_mode,
            state_status="ACTIVE",
            kill_switch_active=self.state.kill_switch_active,
            cooldown_active=False,
            attack_mode_active=False,
            reason=reason,
            actor=actor,
            correlation_id=correlation_id,
            metadata_json=metadata or {},
            system_power=self.state.system_power,
        )
        return self.state


def test_paper_simulation_status_is_disabled_by_default() -> None:
    record = PaperSimulationControlService(governor=_Governor()).status_record(include_paper_truth=False)

    assert record.enabled is False
    assert record.status == "DISABLED"
    assert record.live_execution_enabled is False


def test_enable_requires_actor_and_reason() -> None:
    record = PaperSimulationControlService(governor=_Governor()).enable(PaperSimulationActionRequest(actor="", reason=""))

    assert record.status == "REJECTED"
    assert "actor is required" in record.errors
    assert "reason is required" in record.errors


def test_enable_persists_explicit_state_governor_metadata() -> None:
    governor = _Governor()
    record = PaperSimulationControlService(governor=governor).enable(PaperSimulationActionRequest(actor="operator", reason="paper sim"))

    assert record.enabled is True
    assert record.status == "ENABLED"
    assert governor.actions == ["CONTROL_CENTER_ENABLE_PAPER_SIMULATION"]
    assert governor.state.metadata_json["paper_simulation"]["enabled"] is True
    assert governor.state.metadata_json["paper_simulation"]["paper_only"] is True


def test_enable_is_locked_during_kill() -> None:
    record = PaperSimulationControlService(governor=_Governor(mode=RuntimeMode.KILL, kill=True)).enable(
        PaperSimulationActionRequest(actor="operator", reason="paper sim")
    )

    assert record.status == "LOCKED"
    assert record.enabled is False
    assert "KILL state is active" in " ".join(record.warnings)
