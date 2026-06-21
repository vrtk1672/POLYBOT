from __future__ import annotations

from types import SimpleNamespace

from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.runtime_supervisor import RuntimeSupervisorRecord, RuntimeSupervisorService
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


class _LiveSettings:
    live_trading_enabled = False


class _Governor:
    def __init__(self, *, mode: RuntimeMode = RuntimeMode.DATA_ONLY, power: SystemPower = SystemPower.ON) -> None:
        self.state = RuntimeState(
            current_mode=mode,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=power,
            metadata_json={},
        )
        self.transitions: list[dict[str, str]] = []

    def get_current_state(self) -> RuntimeState:
        return self.state

    def get_permissions(self) -> RuntimePermissions:
        return RuntimePermissions(can_collect_data=True, can_run_intelligence=True, can_run_paper_simulation=True)

    def can_execute(self, action, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value, RuntimeAction.RUN_PAPER_SIMULATION.value}

    def request_mode_change(self, to_mode, *, actor: str, reason: str, metadata=None, correlation_id=None, action: str = "REQUEST_MODE_CHANGE") -> RuntimeState:
        target = RuntimeMode(str(to_mode).strip().upper())
        self.transitions.append({"to_mode": target.value, "action": action})
        self.state = RuntimeState(
            current_mode=target,
            previous_mode=self.state.current_mode,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason=reason,
            actor=actor,
            metadata_json=metadata or {},
            system_power=SystemPower.ON,
        )
        return self.state


class _SystemPower:
    def __init__(self, governor: _Governor) -> None:
        self.governor = governor

    def turn_on(self, **kwargs):
        self.governor.state.system_power = SystemPower.ON
        return {"transition_id": "on", "system_power": "ON", "current_mode": self.governor.state.current_mode.value}

    def turn_off(self, **kwargs):
        self.governor.state.system_power = SystemPower.OFF
        return {"transition_id": "off", "system_power": "OFF", "current_mode": self.governor.state.current_mode.value}


class _Supervisor:
    def __init__(self, governor: _Governor) -> None:
        self.governor = governor
        self.started_mode = None

    def start(self, payload):
        self.started_mode = self.governor.state.current_mode.value
        return SimpleNamespace(to_action_result=lambda: {"supervisor_status": "RUNNING", "mode": self.started_mode, "cycles_completed": 0})

    def stop(self, payload):
        return SimpleNamespace(to_action_result=lambda: {"supervisor_status": "STOPPED"})


class _PaperControl:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def status_record(self, **kwargs):
        return SimpleNamespace(enabled=self.enabled, status="ENABLED" if self.enabled else "DISABLED", to_action_result=lambda: {"enabled": self.enabled, "status": "ENABLED" if self.enabled else "DISABLED"})

    def is_enabled(self) -> bool:
        return self.enabled

    def force_disable_for_stop(self, **kwargs):
        self.enabled = False
        return self.status_record()


class _PaperOn(_PaperControl):
    def status_record(self, **kwargs):
        return SimpleNamespace(enabled=True, status="ENABLED", warnings=[], errors=[])


class _PaperIntents:
    def __init__(self) -> None:
        self.calls = 0

    def build_intents(self, **kwargs):
        self.calls += 1
        return {"paper_intents_created": 1, "paper_intents_updated": 0, "blocked_candidates": 0, "no_trade_records_created": 0, "no_trade_records_updated": 0}


class _PaperExecution:
    def __init__(self) -> None:
        self.calls = 0

    def run_execution(self, **kwargs):
        self.calls += 1
        return {"status": "OK", "orders_created": 1, "fills_created": 1, "positions_created": 1, "block_reasons": {}}


class _PaperExits:
    def run_exit_loop(self, **kwargs):
        return {"status": "OK", "marked_positions_count": 0, "closed_positions_count": 0}

    def get_pnl_dashboard_summary(self, **kwargs):
        return {"status": "OK", "realized_pnl": 0, "unrealized_pnl": 0}


class _Query:
    def overview(self):
        return {"status": "REAL", "data": {"total_markets": 1}, "warnings": [], "errors": []}

    live_flow = organs = closest_actionable = risk_evidence = positions = lifecycle_governance = pnl_ledger = no_trade = ai = logs = truth_state = overview


def test_system_on_mode_paper_sets_governor_and_supervisor(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    governor = _Governor(mode=RuntimeMode.DATA_ONLY, power=SystemPower.OFF)
    supervisor = _Supervisor(governor)
    service = ControlCenterActionService(
        governor=governor,
        system_power=_SystemPower(governor),
        runtime_supervisor=supervisor,
        paper_simulation=_PaperControl(False),
    )

    envelope = service.execute(
        "system-on",
        ControlCenterActionRequest(
            actor="operator",
            reason="paper mode",
            metadata={"requested_execution_mode": "PAPER"},
        ),
    )

    assert envelope.status == "ACCEPTED"
    assert envelope.result["safe_monitoring_mode"]["to_mode"] == "PAPER"
    assert supervisor.started_mode == "PAPER"
    assert governor.state.current_mode == RuntimeMode.PAPER


def test_supervisor_activates_paper_hooks_in_paper_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    governor = _Governor(mode=RuntimeMode.PAPER, power=SystemPower.ON)
    intents = _PaperIntents()
    execution = _PaperExecution()
    supervisor = RuntimeSupervisorService(
        governor=governor,
        query_service=_Query(),
        paper_simulation=_PaperOn(True),
        paper_intents=intents,
        paper_execution=execution,
        paper_exits=_PaperExits(),
        run_in_background=False,
        report_dir=tmp_path,
    )
    record = RuntimeSupervisorRecord(
        supervisor_status="RUNNING",
        session_id="test-paper-supervisor",
        system_power="ON",
        mode="PAPER",
        cycles_completed=0,
    )

    paper_flow = supervisor._execute_paper_cycle(record)

    assert paper_flow["paper_execution_enabled"] is True
    assert paper_flow["paper_intents_created"] == 1
    assert paper_flow["paper_orders_created"] == 1
    assert intents.calls == 1
    assert execution.calls == 1
