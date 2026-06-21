from __future__ import annotations

from pathlib import Path

from app.control_center.action_contract import ControlCenterActionRequest
from app.control_center.action_service import ControlCenterActionService
from app.control_center.full_monitor_run import FullMonitorRunRequest
from app.control_center.full_monitor_run_service import FullMonitorRunService, FullMonitorRunStore
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


class _LiveSettings:
    live_trading_enabled = False


class _LiveEnabledSettings:
    live_trading_enabled = True


class _Governor:
    def __init__(
        self,
        *,
        mode: RuntimeMode = RuntimeMode.DATA_ONLY,
        kill: bool = False,
        live_orders_allowed: bool = False,
    ) -> None:
        self.live_orders_allowed = live_orders_allowed
        self.state = RuntimeState(
            current_mode=mode,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=kill,
            cooldown_active=False,
            attack_mode_active=False,
            reason="stage17",
            actor="certification",
            system_power=SystemPower.ON,
        )

    def get_current_state(self) -> RuntimeState:
        return self.state

    def get_permissions(self) -> RuntimePermissions:
        return RuntimePermissions(can_collect_data=True, can_score_opportunities=True, can_run_intelligence=True)

    def can_execute(self, action: RuntimeAction | str, metadata=None) -> bool:
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        if value == RuntimeAction.SEND_LIVE_ORDER.value:
            return self.live_orders_allowed
        if self.state.current_mode == RuntimeMode.KILL or self.state.kill_switch_active:
            return False
        return value in {RuntimeAction.COLLECT_DATA.value, RuntimeAction.RUN_INTELLIGENCE.value}


class _QueryService:
    def overview(self):
        return _envelope("runtime_state", {"total_markets": 2, "source_counts": {"market_snapshots": 2}})

    def live_flow(self):
        return _envelope("event_log", {"events": [{"id": "event-1"}]})

    def organs(self):
        return _envelope("service_health", {"services": [{"service_name": "runtime"}]})

    def closest_actionable(self):
        return _envelope("risk_evidence", {"candidates": [{"truth_state": "ACTIVE_FRESH"}]})

    def risk_evidence(self):
        return _envelope("risk_evidence_mesh", {"count": 1})

    def positions(self):
        return _envelope("paper_positions", {"positions": []})

    def lifecycle_governance(self):
        return _envelope("lifecycle_governance", {"decisions": []})

    def pnl_ledger(self):
        return _envelope("paper_pnl_ledger", {"rows": []})

    def no_trade(self):
        return _envelope("no_trade_log", {"records": []})

    def ai(self):
        return _envelope("ai_context_router", {"runs": []})

    def logs(self):
        return _envelope("runtime_incidents:event_log", {"runtime_incidents": []})

    def truth_state(self):
        return _envelope("truth_state_registry", {"records": []})


def _envelope(source: str, data: dict):
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


def _monitor_service(monkeypatch, *, governor: _Governor | None = None) -> FullMonitorRunService:
    monkeypatch.setattr("app.control_center.full_monitor_run_service.get_stage4_settings", lambda: _LiveSettings())
    return FullMonitorRunService(
        governor=governor or _Governor(),
        query_service=_QueryService(),
        store=FullMonitorRunStore(),
        run_in_background=False,
        report_dir="run_reports/control_center_monitor_runs_test",
        sleep_between_cycles=False,
    )


def test_full_monitor_run_certifies_zero_execution_counters_and_skipped_execution_modules(monkeypatch) -> None:
    run = _monitor_service(monkeypatch).start(
        FullMonitorRunRequest(actor="operator", reason="stage 17 safety certification", duration_minutes=5, interval_seconds=10)
    )

    assert run.status == "COMPLETED"
    assert run.audit_id and run.audit_id.startswith("control_center_full_monitor_run:")
    assert run.paper_orders == 0
    assert run.paper_fills == 0
    assert run.positions_updated == 0
    assert run.events_created == 0

    module_status = {result.module: result.status for result in run.module_results}
    assert module_status["paper_execution"] == "SKIPPED"
    assert module_status["live_execution"] == "SKIPPED"
    assert module_status["orderbook"] == "SKIPPED"
    assert module_status["news"] == "SKIPPED"
    assert module_status["whale"] == "SKIPPED"
    assert module_status["social"] == "SKIPPED"


def test_full_monitor_run_start_locks_when_live_order_permission_is_available(monkeypatch) -> None:
    run = _monitor_service(monkeypatch, governor=_Governor(live_orders_allowed=True)).start(
        FullMonitorRunRequest(actor="operator", reason="live permission guard", duration_minutes=5, interval_seconds=10)
    )

    assert run.status == "LOCKED"
    assert "permissions allow live orders" in run.warnings[0]


def test_full_monitor_run_start_locks_when_live_trading_setting_is_enabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.control_center.full_monitor_run_service.get_stage4_settings",
        lambda: _LiveEnabledSettings(),
    )
    run = FullMonitorRunService(
        governor=_Governor(),
        query_service=_QueryService(),
        store=FullMonitorRunStore(),
    ).start(FullMonitorRunRequest(actor="operator", reason="live setting guard", duration_minutes=5, interval_seconds=10))

    assert run.status == "LOCKED"
    assert "LIVE_TRADING_ENABLED is true" in run.warnings[0]


def test_control_actions_stay_wrapper_only_and_locked_without_certified_contract(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.action_service.get_stage4_settings", lambda: _LiveSettings())
    service = ControlCenterActionService(governor=_Governor(), system_power=None, full_monitor_run=_monitor_service(monkeypatch))

    missing_fields = service.execute("system-on", ControlCenterActionRequest(actor="", reason=""))
    reset = service.execute(
        "reset-paper-balance",
        ControlCenterActionRequest(
            actor="operator",
            reason="certify locked reset",
            confirmation="RESET PAPER BALANCE",
        ),
    )
    start_without_duration = service.execute(
        "start-full-monitor-run",
        ControlCenterActionRequest(actor="operator", reason="missing duration"),
    )

    assert missing_fields.status == "REJECTED"
    assert "actor is required" in missing_fields.errors
    assert "reason is required" in missing_fields.errors
    assert reset.status == "LOCKED"
    assert reset.audit_id is None
    assert "No safe paper-only balance reset contract" in reset.warnings[0]
    assert start_without_duration.status == "REJECTED"
    assert "duration_minutes is required" in start_without_duration.errors


def test_control_center_source_has_no_direct_execution_or_manual_trade_calls() -> None:
    root = Path("app/control_center")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))

    forbidden = [
        "manual_trade",
        "approve_trade",
        "override_blocker",
        "disable_risk",
        "disable_governance",
        "create_order",
        "create_fill",
        "create_position",
        "submit_live_order",
        "place_live_order",
    ]

    for marker in forbidden:
        assert marker not in combined
