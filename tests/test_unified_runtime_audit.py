from __future__ import annotations

from types import SimpleNamespace

from app.control_center.runtime_supervisor import RuntimeSupervisorService, RuntimeSupervisorStartRequest, RuntimeSupervisorStore
from app.runtime.contracts import RuntimeState
from app.runtime.modes import RuntimeAction, RuntimeMode, RuntimePermissions
from app.runtime.system_power import SystemPower


class _Governor:
    def __init__(self) -> None:
        self.state = RuntimeState(
            current_mode=RuntimeMode.DATA_ONLY,
            previous_mode=None,
            state_status="ACTIVE",
            kill_switch_active=False,
            cooldown_active=False,
            attack_mode_active=False,
            reason="test",
            actor="test",
            system_power=SystemPower.ON,
        )

    def get_current_state(self):
        return self.state

    def get_permissions(self):
        return RuntimePermissions(can_collect_data=True, can_score_opportunities=True, can_run_intelligence=True, can_run_paper_simulation=True)

    def can_execute(self, action, metadata=None):
        value = action.value if isinstance(action, RuntimeAction) else str(action)
        return value in {
            RuntimeAction.COLLECT_DATA.value,
            RuntimeAction.RUN_INTELLIGENCE.value,
            RuntimeAction.RUN_PAPER_SIMULATION.value,
        }


class _Query:
    def __getattr__(self, name):
        def _method():
            return {"status": "REAL", "source": name, "data": {}, "warnings": [], "errors": []}

        return _method


class _PaperControl:
    def status_record(self, **kwargs):
        return SimpleNamespace(enabled=True, status="ENABLED", warnings=[], errors=[])


class _PaperIntents:
    def build_intents(self, **kwargs):
        return {"paper_intents_created": 0, "paper_intents_updated": 0, "blocked_candidates": 1, "no_trade_records_created": 1, "no_trade_records_updated": 0}


class _PaperExecution:
    def run_execution(self, **kwargs):
        return {"status": "NO_VALID_PAPER_INTENTS", "orders_created": 0, "fills_created": 0, "positions_created": 0, "block_reasons": {"NO_VALID_PAPER_INTENTS": 1}}


class _PaperExits:
    def run_exit_loop(self, **kwargs):
        return {"status": "NO_OPEN_PAPER_POSITIONS", "marked_positions_count": 0, "closed_positions_count": 0}

    def get_pnl_dashboard_summary(self, **kwargs):
        return {"status": "OK", "realized_pnl": 0, "unrealized_pnl": 0}


class _SourceRefresh:
    def run_cycle(self, **kwargs):
        return {
            "status": "OK",
            "sources_checked": 8,
            "sources_refreshed": 5,
            "sources_failed": 0,
            "sources_no_new_data": 3,
            "derived_signals_created": 2,
            "trading_mutation": False,
        }


def test_system_on_runtime_loop_connects_source_refresh_and_paper_adapter(monkeypatch) -> None:
    monkeypatch.setattr("app.control_center.runtime_supervisor.get_stage4_settings", lambda: SimpleNamespace(live_trading_enabled=False))
    supervisor = RuntimeSupervisorService(
        governor=_Governor(),
        query_service=_Query(),
        store=RuntimeSupervisorStore(),
        paper_simulation=_PaperControl(),
        source_refresh_orchestrator=_SourceRefresh(),
        paper_intents=_PaperIntents(),
        paper_execution=_PaperExecution(),
        paper_exits=_PaperExits(),
        run_in_background=False,
        sleep_between_cycles=False,
    )

    result = supervisor.start(RuntimeSupervisorStartRequest(actor="operator", reason="unified runtime audit", interval_seconds=30))

    assert result.supervisor_status in {"RUNNING", "DEGRADED"}
    assert result.source_refresh_orchestrator_state == "ACTIVE"
    assert result.sources_refreshed_this_cycle == 5
    assert result.derived_signals_created_this_cycle == 2
    assert result.paper_simulation_enabled is True
    assert result.paper_execution_enabled is True
    assert result.paper_orders_created == 0
    assert result.execution_enabled is False
    assert result.latest_paper_flow["live_execution_enabled"] is False
