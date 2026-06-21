from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


class _LiveSettings:
    live_trading_enabled = False


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
        )
        self.mode_transitions: list[dict[str, object]] = []

    def get_current_state(self) -> RuntimeState:
        return self.state

    def get_permissions(self) -> RuntimePermissions:
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active or self.state.system_power == SystemPower.OFF:
            return RuntimePermissions()
        return RuntimePermissions(can_collect_data=True, can_score_opportunities=True, can_run_intelligence=True)

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        if self.state.system_power == SystemPower.OFF:
            return False
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value}

    def request_mode_change(self, to_mode, *, actor: str, reason: str, metadata=None, correlation_id=None, action: str = "REQUEST_MODE_CHANGE") -> RuntimeState:
        target = RuntimeMode(str(to_mode).strip().upper())
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active:
            from app.runtime.runtime_errors import RuntimeModeTransitionDenied

            raise RuntimeModeTransitionDenied("KILL is active; SYSTEM ON cannot resume from KILL. Use the explicit runtime resume path after operator review.")
        self.mode_transitions.append({"from_mode": self.state.current_mode.value, "to_mode": target.value, "action": action})
        self.state = RuntimeState(
            current_mode=target,
            previous_mode=self.state.current_mode,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason=reason,
            actor=actor,
            correlation_id=correlation_id,
            metadata_json=metadata or {},
            system_power=self.state.system_power,
        )
        return self.state

    def activate_kill(self, *, actor: str, reason: str, metadata=None, correlation_id=None) -> RuntimeState:
        self.state = RuntimeState(
            current_mode=RuntimeMode.KILL,
            previous_mode=RuntimeMode.DATA_ONLY,
            state_status="ACTIVE",
            kill_switch_active=True,
            cooldown_active=False,
            attack_mode_active=False,
            reason=reason,
            actor=actor,
            correlation_id=correlation_id,
            metadata_json=metadata or {},
            system_power=SystemPower.ON,
        )
        return self.state


class _SystemPower:
    def turn_on(self, *, actor: str, reason: str, correlation_id: str | None = None):
        return {
            "transition_id": "transition-on",
            "system_power": "ON",
            "actor": actor,
            "reason": reason,
            "correlation_id": correlation_id,
            "live_allowed": False,
        }

    def turn_off(self, *, actor: str, reason: str, correlation_id: str | None = None):
        return {
            "transition_id": "transition-off",
            "system_power": "OFF",
            "actor": actor,
            "reason": reason,
            "correlation_id": correlation_id,
            "live_allowed": False,
        }


class _PaperSimulation:
    def __init__(self, enabled: bool = False, status: str | None = None) -> None:
        self.enabled = enabled
        self.status = status or ("ENABLED" if enabled else "DISABLED")

    def status_record(self, **kwargs):
        return SimpleNamespace(
            enabled=self.enabled,
            status=self.status,
            last_changed_at="2026-06-10T00:00:00+00:00",
            warnings=[],
            errors=[],
            to_action_result=lambda: {"enabled": self.enabled, "status": self.status},
        )

    def is_enabled(self) -> bool:
        return self.enabled

    def enable(self, payload):
        self.enabled = True
        self.status = "ENABLED"
        return self.status_record()

    def disable(self, payload):
        self.enabled = False
        self.status = "DISABLED"
        return self.status_record()

    def force_disable_for_stop(self, **kwargs):
        self.enabled = False
        self.status = "DISABLED"
        return self.status_record()


def _service(monkeypatch) -> ControlCenterActionService:
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    return ControlCenterActionService(governor=_Governor(), system_power=_SystemPower(), paper_simulation=_PaperSimulation())


def _service_with(monkeypatch, governor: _Governor) -> ControlCenterActionService:
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    return ControlCenterActionService(governor=governor, system_power=_SystemPower(), paper_simulation=_PaperSimulation())


def test_action_envelope_shape_for_full_monitor_run_action(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute(
        "start-full-monitor-run",
        ControlCenterActionRequest(actor="operator", reason="visibility check", duration_minutes=30, interval_seconds=10),
    )

    payload = envelope.model_dump(mode="json")
    assert set(payload) == {
        "action",
        "status",
        "actor",
        "reason",
        "timestamp",
        "audit_id",
        "state_before",
        "state_after",
        "safety_checks",
        "result",
        "warnings",
        "errors",
    }
    assert payload["status"] == "ACCEPTED"
    assert payload["audit_id"]
    assert payload["result"]["status"] in {"STARTING", "RUNNING", "COMPLETED"}
    assert payload["safety_checks"]


def test_missing_actor_and_reason_are_rejected(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute("system-on", ControlCenterActionRequest(actor="", reason=""))

    assert envelope.status == "REJECTED"
    assert "actor is required" in envelope.errors
    assert "reason is required" in envelope.errors


def test_system_power_action_can_be_accepted_only_with_audit_id(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute(
        "system-off",
        ControlCenterActionRequest(actor="operator", reason="manual system off"),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.audit_id == "transition-off"
    assert envelope.result["live_allowed"] is False
    assert any(check.name == "state_governor_loaded" and check.status == "PASS" for check in envelope.safety_checks)


def test_system_on_downgrades_to_safe_data_only_monitoring_mode(monkeypatch) -> None:
    governor = _Governor(mode=RuntimeMode.PAPER, power=SystemPower.OFF)
    envelope = _service_with(monkeypatch, governor).execute(
        "system-on",
        ControlCenterActionRequest(actor="operator", reason="enable monitor only"),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.result["safe_monitoring_mode"]["from_mode"] == "PAPER"
    assert envelope.result["safe_monitoring_mode"]["to_mode"] == "DATA_ONLY"
    assert envelope.result["safe_monitoring_mode"]["changed"] is True
    assert governor.mode_transitions[0]["action"] == "CONTROL_CENTER_SYSTEM_ON_SAFE_MONITORING"
    assert envelope.state_after["state"]["current_mode"] == "DATA_ONLY"
    assert any(check.name == "safe_monitoring_mode" and check.status == "PASS" for check in envelope.safety_checks)


def test_enable_paper_simulation_is_explicit_paper_only_action(monkeypatch) -> None:
    paper = _PaperSimulation()
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    service = ControlCenterActionService(governor=_Governor(), system_power=_SystemPower(), paper_simulation=paper)

    envelope = service.execute(
        "enable-paper-simulation",
        ControlCenterActionRequest(actor="operator", reason="stage 28 paper simulation"),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.result["paper_simulation"]["enabled"] is True
    assert envelope.result["paper_execution_enabled"] is True
    assert envelope.result["execution_enabled"] is False
    assert envelope.result["live_execution_enabled"] is False
    assert any(check.name == "state_governor_not_bypassed" and check.status == "PASS" for check in envelope.safety_checks)


def test_disable_paper_simulation_turns_off_paper_execution_flag(monkeypatch) -> None:
    paper = _PaperSimulation(enabled=True)
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    service = ControlCenterActionService(governor=_Governor(), system_power=_SystemPower(), paper_simulation=paper)

    envelope = service.execute(
        "disable-paper-simulation",
        ControlCenterActionRequest(actor="operator", reason="stop stage 28 paper simulation"),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.result["paper_simulation"]["enabled"] is False
    assert envelope.result["paper_execution_enabled"] is False
    assert envelope.result["live_execution_enabled"] is False


def test_system_on_does_not_resume_from_kill(monkeypatch) -> None:
    governor = _Governor(mode=RuntimeMode.KILL, power=SystemPower.OFF, kill=True)
    envelope = _service_with(monkeypatch, governor).execute(
        "system-on",
        ControlCenterActionRequest(actor="operator", reason="resume from kill"),
    )

    assert envelope.status == "LOCKED"
    assert "KILL is active" in envelope.warnings[0]
    assert not governor.mode_transitions


def test_kill_switch_requires_confirmation(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute(
        "kill-switch",
        ControlCenterActionRequest(actor="operator", reason="emergency stop", confirmation="CONFIRM"),
    )

    assert envelope.status == "REJECTED"
    assert "confirmation text KILL" in envelope.errors[0]


def test_kill_switch_accepts_only_through_state_governor_with_audit(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute(
        "kill-switch",
        ControlCenterActionRequest(actor="operator", reason="emergency stop", confirmation="KILL"),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.audit_id and envelope.audit_id.startswith("system_state_history:")
    assert envelope.result["current_mode"] == "KILL"
    assert envelope.result["kill_switch_active"] is True


def test_reset_paper_balance_remains_locked_without_safe_backend_contract(monkeypatch) -> None:
    envelope = _service(monkeypatch).execute(
        "reset-paper-balance",
        ControlCenterActionRequest(
            actor="operator",
            reason="paper-only test reset",
            confirmation="RESET PAPER BALANCE",
        ),
    )

    assert envelope.status == "LOCKED"
    assert "No safe paper-only balance reset contract" in envelope.warnings[0]
    assert envelope.audit_id is None


def test_control_action_endpoint_uses_wrapper_and_rejects_missing_actor() -> None:
    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).post(
        "/dashboard/api/v2/control/actions/system-on",
        json={"actor": "", "reason": ""},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["action"] == "system-on"
