from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.runtime_supervisor import RuntimeSupervisorService, RuntimeSupervisorStartRequest, RuntimeSupervisorStore
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

    def get_current_state(self) -> RuntimeState:
        return self.state

    def get_permissions(self) -> RuntimePermissions:
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active or self.state.system_power == SystemPower.OFF:
            return RuntimePermissions()
        return RuntimePermissions(can_collect_data=True, can_score_opportunities=True, can_run_intelligence=True)

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return self.state.system_power == SystemPower.ON and value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value}

    def request_mode_change(self, to_mode, *, actor: str, reason: str, metadata=None, correlation_id=None, action: str = "REQUEST_MODE_CHANGE") -> RuntimeState:
        target = RuntimeMode(str(to_mode).strip().upper())
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active:
            from app.runtime.runtime_errors import RuntimeModeTransitionDenied

            raise RuntimeModeTransitionDenied("KILL is active")
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
            system_power=SystemPower.ON,
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
    def __init__(self, governor: _Governor) -> None:
        self._governor = governor

    def turn_on(self, *, actor: str, reason: str, correlation_id: str | None = None):
        self._governor.state.system_power = SystemPower.ON
        return {"transition_id": "transition-on", "system_power": "ON", "current_mode": self._governor.state.current_mode.value}

    def turn_off(self, *, actor: str, reason: str, correlation_id: str | None = None):
        self._governor.state.system_power = SystemPower.OFF
        return {"transition_id": "transition-off", "system_power": "OFF", "current_mode": self._governor.state.current_mode.value}


class _QueryService:
    def overview(self):
        return _envelope("runtime_state", {"total_markets": 12, "source_counts": {"event_log": 50}})

    def live_flow(self):
        return _envelope("event_log", {"events": [{"id": "event-1"}], "count": 1})

    def organs(self):
        return _envelope("service_health", {"services": [{"service_name": "runtime"}], "count": 1})

    def closest_actionable(self):
        return _envelope("risk_evidence", {"candidates": [{"truth_state": "ACTIVE_FRESH"}], "count": 1})

    def risk_evidence(self):
        return _envelope("risk_evidence_mesh", {"count": 2})

    def positions(self):
        return _envelope("paper_positions", {"positions": []})

    def lifecycle_governance(self):
        return _envelope("lifecycle_governance", {"decisions": []})

    def pnl_ledger(self):
        return _envelope("paper_pnl_ledger", {"rows": []})

    def no_trade(self):
        return _envelope("no_trade_log", {"records": [{"reason": "missing evidence"}], "count": 1})

    def ai(self):
        return _envelope("ai_context_router", {"runs": [{"status": "OK"}]})

    def logs(self):
        return _envelope("runtime_incidents:event_log", {"runtime_incidents": []})

    def truth_state(self):
        return _envelope("truth_state_registry", {"records": []})


class _FailingQueryService(_QueryService):
    def overview(self):
        raise RuntimeError("overview unavailable")


class _PaperControl:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def status_record(self, **kwargs):
        return SimpleNamespace(enabled=self.enabled, status="ENABLED" if self.enabled else "DISABLED", warnings=[], errors=[])

    def is_enabled(self) -> bool:
        return self.enabled


class _PaperIntents:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {"paper_intents_created": 0, "paper_intents_updated": 0, "blocked_candidates": 0, "no_trade_records_created": 0, "no_trade_records_updated": 0}
        self.calls = 0

    def build_intents(self, **kwargs):
        self.calls += 1
        return dict(self.payload)


class _PaperExecution:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {"status": "NO_VALID_PAPER_INTENTS", "orders_created": 0, "fills_created": 0, "positions_created": 0, "block_reasons": {"NO_VALID_PAPER_INTENTS": 1}}
        self.calls = 0

    def run_execution(self, **kwargs):
        self.calls += 1
        return dict(self.payload)


class _PaperExits:
    def __init__(self, run_payload: dict | None = None, pnl_payload: dict | None = None) -> None:
        self.run_payload = run_payload or {"status": "NO_OPEN_PAPER_POSITIONS", "marked_positions_count": 0, "closed_positions_count": 0}
        self.pnl_payload = pnl_payload or {"status": "NO_OPEN_PAPER_POSITIONS", "realized_pnl": 0, "unrealized_pnl": 0}
        self.calls = 0

    def run_exit_loop(self, **kwargs):
        self.calls += 1
        return dict(self.run_payload)

    def get_pnl_dashboard_summary(self, **kwargs):
        return dict(self.pnl_payload)


class _CandidateOrderbookRefresher:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def resolve(self, **kwargs):
        return dict(self.payload)


def _envelope(source: str, data: dict):
    return {
        "status": "REAL",
        "source": source,
        "last_updated": "2026-06-10T00:00:00+00:00",
        "stale_after_seconds": 300,
        "truth_state": "ACTIVE_FRESH",
        "data": data,
        "warnings": [],
        "errors": [],
    }


def _supervisor(monkeypatch, governor: _Governor | None = None, store: RuntimeSupervisorStore | None = None, report_dir=None, run_in_background: bool = False) -> RuntimeSupervisorService:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    return RuntimeSupervisorService(
        governor=governor or _Governor(),
        query_service=_QueryService(),
        store=store or RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(False),
        run_in_background=run_in_background,
        report_dir=report_dir or "run_reports/control_center_supervisor_sessions_test",
        sleep_between_cycles=False,
    )


def test_system_on_starts_runtime_supervisor(monkeypatch) -> None:
    governor = _Governor(mode=RuntimeMode.PAPER, power=SystemPower.OFF)
    supervisor = _supervisor(monkeypatch, governor=governor)
    service = ControlCenterActionService(governor=governor, system_power=_SystemPower(governor), runtime_supervisor=supervisor)

    envelope = service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="stage 27 start", interval_seconds=30))

    assert envelope.status == "ACCEPTED"
    assert envelope.result["system_power"] == "ON"
    assert envelope.result["safe_monitoring_mode"]["to_mode"] == "DATA_ONLY"
    assert envelope.result["supervisor"]["supervisor_status"] in {"RUNNING", "DEGRADED"}
    assert envelope.result["supervisor"]["interval_seconds"] == 30
    assert envelope.result["supervisor"]["cycles_completed"] == 1
    assert envelope.result["execution_enabled"] is False
    assert envelope.result["paper_execution_enabled"] is False


def test_system_on_is_idempotent_when_supervisor_running(monkeypatch) -> None:
    governor = _Governor()
    store = RuntimeSupervisorStore()
    supervisor = _supervisor(monkeypatch, governor=governor, store=store)
    service = ControlCenterActionService(governor=governor, system_power=_SystemPower(governor), runtime_supervisor=supervisor)

    first = service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="start"))
    second = service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="start again"))

    assert second.status == "ACCEPTED"
    assert second.result["supervisor"]["session_id"] == first.result["supervisor"]["session_id"]
    assert "idempotent" in " ".join(second.result["supervisor"]["warnings"])


def test_system_off_stops_supervisor_and_writes_report(monkeypatch, tmp_path) -> None:
    governor = _Governor()
    supervisor = _supervisor(monkeypatch, governor=governor, report_dir=tmp_path)
    service = ControlCenterActionService(governor=governor, system_power=_SystemPower(governor), runtime_supervisor=supervisor)

    service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="start"))
    off = service.execute("system-off", ControlCenterActionRequest(actor="operator", reason="stop"))

    assert off.status == "ACCEPTED"
    assert off.result["system_power"] == "OFF"
    assert off.result["supervisor"]["supervisor_status"] == "STOPPED"
    report_path = off.result["supervisor"]["report_path"]
    assert report_path
    assert Path(report_path).exists()


def test_kill_stops_and_blocks_supervisor(monkeypatch) -> None:
    governor = _Governor()
    supervisor = _supervisor(monkeypatch, governor=governor)
    service = ControlCenterActionService(governor=governor, system_power=_SystemPower(governor), runtime_supervisor=supervisor)

    service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="start"))
    killed = service.execute("kill-switch", ControlCenterActionRequest(actor="operator", reason="emergency", confirmation="KILL"))
    restart = service.execute("system-on", ControlCenterActionRequest(actor="operator", reason="restart"))

    assert killed.status == "ACCEPTED"
    assert killed.result["supervisor"]["supervisor_status"] == "KILLED"
    assert restart.status == "LOCKED"


def test_supervisor_rejects_unsafe_mode_and_preserves_execution_counters(monkeypatch) -> None:
    run = _supervisor(monkeypatch, governor=_Governor(mode=RuntimeMode.SHADOW_LIVE, power=SystemPower.ON)).start(
        RuntimeSupervisorStartRequest(actor="operator", reason="unsafe")
    )

    assert run.supervisor_status == "LOCKED"
    assert "requires DATA_ONLY" in run.warnings[0]
    assert run.paper_orders == 0
    assert run.paper_fills == 0
    assert run.positions_updated == 0


def test_supervisor_does_not_call_paper_services_when_switch_is_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    intents = _PaperIntents()
    execution = _PaperExecution()
    exits = _PaperExits()
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(False),
        paper_intents=intents,
        paper_execution=execution,
        paper_exits=exits,
        run_in_background=False,
        sleep_between_cycles=False,
    )

    run = supervisor.start(RuntimeSupervisorStartRequest(actor="operator", reason="monitor only"))

    assert run.supervisor_status == "RUNNING"
    assert run.paper_simulation_enabled is False
    assert run.paper_orders == 0
    assert intents.calls == 0
    assert execution.calls == 0
    assert exits.calls == 0


def test_supervisor_records_paper_order_fill_position_when_switch_is_enabled(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(True),
        paper_intents=_PaperIntents({"paper_intents_created": 1, "paper_intents_updated": 0, "blocked_candidates": 0, "no_trade_records_created": 0, "no_trade_records_updated": 0}),
        paper_execution=_PaperExecution({"status": "OK", "orders_created": 1, "fills_created": 1, "positions_created": 1, "block_reasons": {}}),
        paper_exits=_PaperExits({"status": "OK", "marked_positions_count": 1, "closed_positions_count": 0}, {"status": "OK", "realized_pnl": 0.25, "unrealized_pnl": 0.5}),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    run = supervisor.start(RuntimeSupervisorStartRequest(actor="operator", reason="paper simulation"))

    assert run.paper_simulation_enabled is True
    assert run.paper_execution_enabled is True
    assert run.paper_intents_created == 1
    assert run.paper_orders_created == 1
    assert run.paper_fills_created == 1
    assert run.paper_positions_opened == 1
    assert run.positions_updated == 2
    assert run.paper_pnl["realized_pnl"] == 0.25
    assert run.last_cycle_summary["paper_simulation"]["paper_orders_created"] == 1
    assert run.execution_enabled is False


def test_supervisor_surfaces_no_trade_blockers_when_paper_candidate_fails(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(True),
        paper_intents=_PaperIntents({"paper_intents_created": 0, "paper_intents_updated": 0, "blocked_candidates": 1, "no_trade_records_created": 1, "no_trade_records_updated": 0}),
        paper_execution=_PaperExecution({"status": "NO_VALID_PAPER_INTENTS", "orders_created": 0, "fills_created": 0, "positions_created": 0, "block_reasons": {"NO_EXIT_PLAN": 1}}),
        paper_exits=_PaperExits(),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    run = supervisor.start(RuntimeSupervisorStartRequest(actor="operator", reason="blocked paper simulation"))

    assert run.paper_simulation_enabled is True
    assert run.paper_intents_blocked == 2
    assert run.paper_orders_created == 0
    assert run.paper_blockers == ["NO_EXIT_PLAN: 1", "NO_VALID_PAPER_INTENTS"]
    assert run.last_cycle_summary["paper_simulation"]["paper_intents_blocked"] == 2


def test_paper_mode_allows_expected_paper_adapter_deltas_in_refresh_monitor(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    payload = {
        "safety_counts_before": {"paper_intents": 0},
        "safety_counts_after": {"paper_intents": 3},
        "trusted_matches_created": 1,
    }
    supervisor = RuntimeSupervisorService(
        governor=_Governor(mode=RuntimeMode.PAPER, power=SystemPower.ON),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(True),
        candidate_orderbook_refresher=_CandidateOrderbookRefresher(payload),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    result = supervisor._run_candidate_orderbook_refresher_module()

    assert result.status == "COMPLETED"
    assert result.errors == []


def test_data_only_still_rejects_paper_adapter_deltas_in_refresh_monitor(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    payload = {
        "safety_counts_before": {"paper_intents": 0},
        "safety_counts_after": {"paper_intents": 1},
        "trusted_matches_created": 1,
    }
    supervisor = RuntimeSupervisorService(
        governor=_Governor(mode=RuntimeMode.DATA_ONLY, power=SystemPower.ON),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(False),
        candidate_orderbook_refresher=_CandidateOrderbookRefresher(payload),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    result = supervisor._run_candidate_orderbook_refresher_module()

    assert result.status == "ERROR"
    assert result.errors == ["UNEXPECTED_PAPER_INTENTS_DELTA:1"]


def test_paper_mode_still_rejects_non_paper_execution_deltas_in_refresh_monitor(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    payload = {
        "safety_counts_before": {"orders_v2": 0},
        "safety_counts_after": {"orders_v2": 1},
        "trusted_matches_created": 1,
    }
    supervisor = RuntimeSupervisorService(
        governor=_Governor(mode=RuntimeMode.PAPER, power=SystemPower.ON),
        query_service=_QueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(True),
        candidate_orderbook_refresher=_CandidateOrderbookRefresher(payload),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    result = supervisor._run_candidate_orderbook_refresher_module()

    assert result.status == "ERROR"
    assert result.errors == ["UNEXPECTED_ORDERS_V2_DELTA:1"]


def test_supervisor_state_endpoint_returns_truth_contract() -> None:
    app = FastAPI()
    app.include_router(create_router())
    response = TestClient(app).get("/dashboard/api/v2/control/runtime-supervisor")

    assert response.status_code == 200
    assert response.json()["source"] == "control_center:runtime_supervisor"
    assert response.json()["data"]["supervisor_available"] is True
    assert response.json()["data"]["execution_enabled"] is False


def test_supervisor_records_cycle_errors_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: _LiveSettings())
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_FailingQueryService(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(False),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    run = supervisor.start(RuntimeSupervisorStartRequest(actor="operator", reason="degrade safely"))

    assert run.supervisor_status == "DEGRADED"
    assert run.cycles_completed == 1
    assert any("overview unavailable" in error for error in run.errors)
    assert run.paper_orders == 0
    assert run.paper_fills == 0
    assert run.positions_updated == 0
