from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_router
from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.full_monitor_run import FullMonitorRunRecord, FullMonitorRunRequest, FullMonitorStopRequest, utc_now_iso
from app.control_center.full_monitor_run_service import FullMonitorRunService, FullMonitorRunStore
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


class _LiveSettings:
    live_trading_enabled = False


class _Governor:
    def __init__(self, mode: RuntimeMode = RuntimeMode.DATA_ONLY, kill: bool = False, power: SystemPower = SystemPower.ON) -> None:
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
        return RuntimePermissions(can_collect_data=True, can_score_opportunities=True, can_run_intelligence=True)

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active or self.state.system_power == SystemPower.OFF:
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
            system_power=SystemPower.ON,
        )
        return self.state


class _QueryService:
    def overview(self):
        return _envelope("overview", "runtime_state", {"total_markets": 12, "source_counts": {"market_snapshots": 12}})

    def live_flow(self):
        return _envelope("live_flow", "event_log", {"events": [{"id": "event-1"}], "count": 1})

    def organs(self):
        return _envelope("organs", "service_health", {"services": [{"service_name": "runtime"}], "count": 1})

    def closest_actionable(self):
        return _envelope("closest_actionable", "risk_evidence", {"candidates": [{"truth_state": "ACTIVE_FRESH"}]})

    def risk_evidence(self):
        return _envelope("risk", "risk_evidence_mesh", {"count": 2})

    def positions(self):
        return _envelope("positions", "paper_positions", {"positions": []})

    def lifecycle_governance(self):
        return _envelope("lifecycle", "lifecycle_governance", {"decisions": []})

    def pnl_ledger(self):
        return _envelope("pnl", "paper_pnl_ledger", {"rows": []})

    def no_trade(self):
        return _envelope("no_trade", "no_trade_log", {"records": [{"reason": "missing evidence"}], "count": 1})

    def ai(self):
        return _envelope("ai", "ai_context_router", {"runs": []})

    def logs(self):
        return _envelope("logs", "runtime_incidents:event_log", {"runtime_incidents": []})

    def truth_state(self):
        return _envelope("truth_state", "truth_state_registry", {"records": []})


def _envelope(name: str, source: str, data: dict):
    return {
        "status": "REAL",
        "source": source,
        "last_updated": "2026-06-08T00:00:00+00:00",
        "stale_after_seconds": 300,
        "truth_state": "ACTIVE_FRESH",
        "data": data,
        "warnings": [],
        "errors": [],
    }


def _service(monkeypatch, governor: _Governor | None = None, store: FullMonitorRunStore | None = None, report_dir=None, run_in_background: bool = False) -> FullMonitorRunService:
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    return FullMonitorRunService(
        governor=governor or _Governor(),
        query_service=_QueryService(),
        store=store or FullMonitorRunStore(),
        run_in_background=run_in_background,
        report_dir=report_dir or "run_reports/control_center_monitor_runs_test",
        sleep_between_cycles=False,
    )


def test_full_monitor_run_contract_shape_and_counters(monkeypatch) -> None:
    run = _service(monkeypatch).start(
        FullMonitorRunRequest(actor="operator", reason="monitor whole body", duration_minutes=5, interval_seconds=10)
    )

    payload = run.model_dump(mode="json")
    for field in [
        "run_id",
        "status",
        "started_at",
        "requested_duration_minutes",
        "interval_seconds",
        "elapsed_seconds",
        "remaining_seconds",
        "cycles_completed",
        "markets_checked",
        "events_created",
        "events_seen",
        "opportunities_found",
        "no_trades_logged",
        "paper_orders",
        "paper_fills",
        "positions_updated",
        "module_results",
        "errors",
        "warnings",
        "audit_id",
        "report_path",
        "safety_mode",
        "execution_enabled",
    ]:
        assert field in payload
    assert run.status == "COMPLETED"
    assert run.cycles_completed == 1
    assert run.markets_checked == 12
    assert run.opportunities_found == 1
    assert run.no_trades_logged == 1
    assert run.paper_orders == 0
    assert run.paper_fills == 0
    assert run.positions_updated == 0
    assert run.execution_enabled is False
    assert run.safety_mode == "DATA_ONLY_MONITORING"


def test_start_requires_actor_reason_and_duration(monkeypatch) -> None:
    run = _service(monkeypatch).start(FullMonitorRunRequest(actor="", reason="", duration_minutes=None, interval_seconds=None))

    assert run.status == "REJECTED"
    assert "actor is required" in run.errors
    assert "reason is required" in run.errors
    assert "duration_minutes is required" in run.errors
    assert "interval_seconds is required" in run.errors


def test_invalid_duration_is_rejected_by_contract() -> None:
    response = TestClient(_action_app()).post(
        "/dashboard/api/v2/control/actions/start-full-monitor-run",
        json={"actor": "operator", "reason": "too long", "duration_minutes": 61, "interval_seconds": 10},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "duration_minutes must be between 1 and 60" in response.json()["errors"]


def test_invalid_interval_is_rejected_by_contract() -> None:
    response = TestClient(_action_app()).post(
        "/dashboard/api/v2/control/actions/start-full-monitor-run",
        json={"actor": "operator", "reason": "too fast", "duration_minutes": 1, "interval_seconds": 5},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert "interval_seconds must be between 10 and 300" in response.json()["errors"]


def test_kill_blocks_start(monkeypatch) -> None:
    run = _service(monkeypatch, governor=_Governor(mode=RuntimeMode.KILL, kill=True)).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "LOCKED"
    assert "KILL state is active" in run.warnings[0]


def test_system_power_off_blocks_start(monkeypatch) -> None:
    run = _service(monkeypatch, governor=_Governor(mode=RuntimeMode.DATA_ONLY, power=SystemPower.OFF)).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "LOCKED"
    assert "State Governor does not allow monitoring/data collection" in run.warnings[0]


def test_full_monitor_run_allowed_after_safe_monitoring_transition(monkeypatch) -> None:
    governor = _Governor(mode=RuntimeMode.PAPER, power=SystemPower.OFF)
    governor.request_mode_change(
        RuntimeMode.DATA_ONLY,
        actor="operator",
        reason="safe monitoring transition",
        metadata={"safe_monitoring_only": True},
        action="CONTROL_CENTER_SYSTEM_ON_SAFE_MONITORING",
    )

    run = _service(monkeypatch, governor=governor).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "COMPLETED"
    assert governor.state.current_mode == RuntimeMode.DATA_ONLY
    assert run.paper_orders == 0
    assert run.paper_fills == 0
    assert run.positions_updated == 0


def test_paper_mode_is_not_enough_for_stage25_monitoring(monkeypatch) -> None:
    run = _service(monkeypatch, governor=_Governor(mode=RuntimeMode.PAPER, power=SystemPower.ON)).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "LOCKED"
    assert "requires DATA_ONLY" in run.warnings[0]


def test_unsafe_modules_are_skipped_not_forced(monkeypatch) -> None:
    run = _service(monkeypatch).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    skipped = {result.module: result for result in run.module_results if result.status == "SKIPPED"}
    assert "orderbook" in skipped
    assert "news" in skipped
    assert "whale" in skipped
    assert "social" in skipped
    assert "paper_execution" in skipped
    assert "live_execution" in skipped


def test_stop_requires_actor_and_reason(monkeypatch) -> None:
    run = _service(monkeypatch).stop(FullMonitorStopRequest(actor="", reason=""))

    assert run.status == "REJECTED"
    assert "actor is required" in run.errors
    assert "reason is required" in run.errors


def test_stop_handles_no_active_run_safely(monkeypatch) -> None:
    run = _service(monkeypatch).stop(FullMonitorStopRequest(actor="operator", reason="done"))

    assert run.status == "STOPPED"
    assert "No active Full Monitor Run exists" in run.warnings[0]


def test_stop_marks_existing_running_run_stopped(monkeypatch) -> None:
    store = FullMonitorRunStore()
    store.set_current(
        FullMonitorRunRecord(
            run_id="full_monitor_run_active",
            status="RUNNING",
            started_at=utc_now_iso(),
            requested_duration_minutes=10,
            duration_minutes=10,
            interval_seconds=10,
            audit_id="audit-active",
            actor="operator",
            reason="monitor",
        )
    )
    run = _service(monkeypatch, store=store).stop(FullMonitorStopRequest(actor="operator", reason="stop"))

    assert run.status == "STOPPED"
    assert run.stopped_at is not None
    assert store.get_current() is None


def test_cannot_start_second_run_while_active(monkeypatch) -> None:
    store = FullMonitorRunStore()
    store.set_current(
        FullMonitorRunRecord(
            run_id="full_monitor_run_active",
            status="RUNNING",
            started_at=utc_now_iso(),
            requested_duration_minutes=10,
            duration_minutes=10,
            interval_seconds=10,
            audit_id="audit-active",
            actor="operator",
            reason="monitor",
        )
    )

    run = _service(monkeypatch, store=store).start(
        FullMonitorRunRequest(actor="operator", reason="monitor", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "LOCKED"
    assert "already running" in run.warnings[0]


def test_completed_run_writes_report_file_with_safety_summary(monkeypatch, tmp_path) -> None:
    run = _service(monkeypatch, report_dir=tmp_path).start(
        FullMonitorRunRequest(actor="operator", reason="report", duration_minutes=1, interval_seconds=10)
    )

    assert run.status == "COMPLETED"
    assert run.report_path
    report = Path(run.report_path).read_text(encoding="utf-8")
    assert "Safety Summary" in report
    assert "Monitoring only. No paper execution enabled in this phase." in report
    assert "No live trading, orders, fills, or positions" in report


def test_action_wrapper_activates_start_and_stop(monkeypatch) -> None:
    store = FullMonitorRunStore()
    full_monitor = _service(monkeypatch, store=store)
    action_service = ControlCenterActionService(
        governor=_Governor(),
        system_power=None,  # not used by this test
        full_monitor_run=full_monitor,
    )

    start = action_service.execute(
            "start-full-monitor-run",
            ControlCenterActionRequest(actor="operator", reason="monitor", duration_minutes=5, interval_seconds=10),
        )
    assert start.status == "ACCEPTED"
    assert start.audit_id
    assert start.result["run_id"].startswith("full_monitor_run_")
    assert start.result["status"] == "COMPLETED"

    stop = action_service.execute(
        "stop-current-run",
        ControlCenterActionRequest(actor="operator", reason="stop"),
    )
    assert stop.status == "ACCEPTED"
    assert stop.result["status"] == "STOPPED"


def test_status_endpoint_returns_truth_contract() -> None:
    client = TestClient(_action_app())
    response = client.get("/dashboard/api/v2/control/full-monitor-run")

    assert response.status_code == 200
    assert response.json()["status"] in {"MISSING", "REAL", "PARTIAL"}
    assert response.json()["data"]["run_type"] == "FULL_MONITOR_RUN"
    assert response.json()["data"]["available"] is True
    assert response.json()["data"]["execution_enabled"] is False


def _action_app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_router())
    return app
