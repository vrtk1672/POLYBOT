from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.control_center.full_monitor_run_service import _unique
from app.control_center.truth_contract import truth_envelope
from app.db.connection import DatabaseConnectionFactory
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.runtime_errors import RuntimeModeTransitionDenied, RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor
from app.runtime.system_power import SystemPower
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from app.services.paper_execution import PaperExecutionService
from app.services.paper_exit_loop import PaperExitLoopService
from app.services.paper_intents import PaperIntentGateService
from app.stage4 import get_stage4_settings
from app.utils.json_safety import json_safe


PaperSimulationStatus = Literal["ENABLED", "DISABLED", "LOCKED", "REJECTED", "ERROR"]


class PaperSimulationActionRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")


class PaperSimulationRecord(BaseModel):
    enabled: bool = False
    status: PaperSimulationStatus = "DISABLED"
    actor: str | None = None
    reason: str | None = None
    last_changed_at: str | None = None
    mode: str = "UNKNOWN"
    system_power: str = "UNKNOWN"
    paper_execution_label: str = "PAPER SIMULATION ONLY"
    execution_enabled: bool = False
    live_execution_enabled: bool = False
    paper_only: bool = True
    simulated_only: bool = True
    latest_paper_order: dict[str, Any] | None = None
    latest_paper_fill: dict[str, Any] | None = None
    latest_paper_position: dict[str, Any] | None = None
    paper_pnl: dict[str, Any] = Field(default_factory=dict)
    paper_execution: dict[str, Any] = Field(default_factory=dict)
    paper_intents: dict[str, Any] = Field(default_factory=dict)
    no_trade: dict[str, Any] = Field(default_factory=dict)
    positions: dict[str, Any] = Field(default_factory=dict)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def to_action_result(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class PaperSimulationControlService:
    """Explicit operator control for Stage 28 paper simulation.

    This is intentionally separate from SYSTEM ON. SYSTEM ON starts monitoring;
    this service decides whether the runtime supervisor is allowed to call the
    existing paper intent/execution/exit simulation services.
    """

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)

    def enable(self, payload: PaperSimulationActionRequest) -> PaperSimulationRecord:
        errors = _validate_operator(payload.actor, payload.reason)
        if errors:
            return PaperSimulationRecord(status="REJECTED", actor=payload.actor.strip(), reason=payload.reason.strip(), errors=errors)
        lock_reason = self._lock_reason(require_power_on=True)
        if lock_reason:
            record = self.status_record()
            record.status = "LOCKED"
            record.enabled = False
            record.warnings = _unique([*record.warnings, lock_reason])
            record.actor = payload.actor.strip()
            record.reason = payload.reason.strip()
            return record
        try:
            state = self._governor.get_current_state()
            metadata = dict(state.metadata_json or {})
            paper_meta = dict(metadata.get("paper_simulation") or {})
            paper_meta.update(
                {
                    "enabled": True,
                    "actor": payload.actor.strip(),
                    "reason": payload.reason.strip(),
                    "last_changed_at": datetime.now(UTC).isoformat(),
                    "stage": 28,
                    "paper_only": True,
                    "simulated_only": True,
                    "execution_mode": RuntimeMode.PAPER.value,
                    "live_adapter_enabled": False,
                }
            )
            metadata["paper_simulation"] = paper_meta
            metadata["execution_mode"] = RuntimeMode.PAPER.value
            metadata["paper_is_execution_adapter_only"] = True
            metadata["live_adapter_enabled"] = False
            state = self._governor.request_mode_change(
                RuntimeMode.PAPER,
                actor=payload.actor,
                reason=f"Control Center PAPER SIMULATION ON: {payload.reason}",
                metadata=metadata,
                correlation_id=f"control_center_paper_simulation_on_{uuid4().hex}",
                action="CONTROL_CENTER_ENABLE_PAPER_SIMULATION",
            )
            return self.status_record(state_override=state)
        except RuntimeModeTransitionDenied as exc:
            return PaperSimulationRecord(status="LOCKED", actor=payload.actor.strip(), reason=payload.reason.strip(), warnings=[str(exc)])
        except Exception as exc:
            return PaperSimulationRecord(status="ERROR", actor=payload.actor.strip(), reason=payload.reason.strip(), errors=[f"{type(exc).__name__}: {exc}"])

    def disable(self, payload: PaperSimulationActionRequest) -> PaperSimulationRecord:
        errors = _validate_operator(payload.actor, payload.reason)
        if errors:
            return PaperSimulationRecord(status="REJECTED", actor=payload.actor.strip(), reason=payload.reason.strip(), errors=errors)
        try:
            state = self._governor.get_current_state()
            if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
                return self._disabled_without_transition(payload, warning="KILL is active; paper simulation is treated as disabled.")
            metadata = dict(state.metadata_json or {})
            paper_meta = dict(metadata.get("paper_simulation") or {})
            paper_meta.update(
                {
                    "enabled": False,
                    "actor": payload.actor.strip(),
                    "reason": payload.reason.strip(),
                    "last_changed_at": datetime.now(UTC).isoformat(),
                    "stage": 28,
                    "paper_only": True,
                    "simulated_only": True,
                    "execution_mode": RuntimeMode.DATA_ONLY.value,
                    "live_adapter_enabled": False,
                }
            )
            metadata["paper_simulation"] = paper_meta
            metadata["execution_mode"] = RuntimeMode.DATA_ONLY.value
            metadata["paper_is_execution_adapter_only"] = False
            metadata["live_adapter_enabled"] = False
            state = self._governor.request_mode_change(
                RuntimeMode.DATA_ONLY,
                actor=payload.actor,
                reason=f"Control Center PAPER SIMULATION OFF: {payload.reason}",
                metadata=metadata,
                correlation_id=f"control_center_paper_simulation_off_{uuid4().hex}",
                action="CONTROL_CENTER_DISABLE_PAPER_SIMULATION",
            )
            return self.status_record(state_override=state)
        except Exception as exc:
            return PaperSimulationRecord(status="ERROR", actor=payload.actor.strip(), reason=payload.reason.strip(), errors=[f"{type(exc).__name__}: {exc}"])

    def force_disable_for_stop(self, *, actor: str, reason: str) -> PaperSimulationRecord:
        return self.disable(PaperSimulationActionRequest(actor=actor, reason=reason))

    def is_enabled(self) -> bool:
        record = self.status_record(include_paper_truth=False)
        return bool(record.enabled and record.status == "ENABLED")

    def status(self) -> dict[str, Any]:
        record = self.status_record()
        envelope_status = "REAL" if record.status in {"ENABLED", "DISABLED"} else record.status
        truth_state = "ACTIVE_FRESH" if record.status == "ENABLED" else "LAST_KNOWN"
        if record.status in {"LOCKED", "REJECTED", "ERROR"}:
            truth_state = "REFRESH_REQUIRED"
        return truth_envelope(
            status=envelope_status,
            source="control_center:paper_simulation",
            truth_state=truth_state,
            data=record.to_action_result(),
            last_updated=record.last_changed_at or datetime.now(UTC),
            stale_after_seconds=300,
            warnings=record.warnings,
            errors=record.errors,
        ).to_dict()

    def status_record(self, *, state_override: Any | None = None, include_paper_truth: bool = True) -> PaperSimulationRecord:
        warnings: list[str] = []
        errors: list[str] = []
        try:
            state = state_override or self._governor.get_current_state()
            mode = state.current_mode.value
            power = state.system_power.value
            metadata = dict(state.metadata_json or {})
            paper_meta = dict(metadata.get("paper_simulation") or {})
            enabled = bool(paper_meta.get("enabled"))
            if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
                enabled = False
                warnings.append("KILL is active; paper simulation is disabled.")
            if state.system_power == SystemPower.OFF:
                enabled = False
                warnings.append("System power is OFF; paper simulation cannot run.")
            status: PaperSimulationStatus = "ENABLED" if enabled else "DISABLED"
            actor = paper_meta.get("actor")
            reason = paper_meta.get("reason")
            changed_at = paper_meta.get("last_changed_at") or state.last_transition_at
        except RuntimeStateUnavailable as exc:
            return PaperSimulationRecord(status="LOCKED", warnings=[f"State Governor unavailable: {exc}"])
        except Exception as exc:
            return PaperSimulationRecord(status="ERROR", errors=[f"{type(exc).__name__}: {exc}"])

        record = PaperSimulationRecord(
            enabled=enabled,
            status=status,
            actor=str(actor) if actor is not None else None,
            reason=str(reason) if reason is not None else None,
            last_changed_at=changed_at.isoformat() if hasattr(changed_at, "isoformat") else (str(changed_at) if changed_at else None),
            mode=mode,
            system_power=power,
            warnings=warnings,
            errors=errors,
        )
        if include_paper_truth:
            self._attach_paper_truth(record)
        return record

    def _lock_reason(self, *, require_power_on: bool) -> str | None:
        try:
            state = self._governor.get_current_state()
        except Exception as exc:
            return f"State Governor unavailable: {exc}"
        if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            return "KILL state is active; paper simulation cannot be enabled."
        if state.current_mode not in {RuntimeMode.DATA_ONLY, RuntimeMode.PAPER}:
            return "Paper simulation control requires DATA_ONLY or PAPER runtime mode."
        if require_power_on and state.system_power == SystemPower.OFF:
            return "SYSTEM ON is required before enabling paper simulation."
        if not self._governor.can_execute(RuntimeAction.RUN_PAPER_SIMULATION):
            return "State Governor does not allow RUN_PAPER_SIMULATION."
        try:
            if bool(get_stage4_settings().live_trading_enabled):
                return "LIVE_TRADING_ENABLED is true; paper simulation control is locked."
        except Exception as exc:
            return f"Live safety settings could not be loaded: {exc}"
        return None

    def _disabled_without_transition(self, payload: PaperSimulationActionRequest, *, warning: str) -> PaperSimulationRecord:
        record = self.status_record()
        record.enabled = False
        record.status = "DISABLED"
        record.actor = payload.actor.strip()
        record.reason = payload.reason.strip()
        record.warnings = _unique([*record.warnings, warning])
        return record

    def _attach_paper_truth(self, record: PaperSimulationRecord) -> None:
        try:
            intent_payload = PaperIntentGateService(connection_factory=self._factory).get_dashboard_summary(limit=20)
            no_trade_payload = PaperIntentGateService(connection_factory=self._factory).get_no_trade_dashboard_summary(limit=20)
            execution_payload = PaperExecutionService(connection_factory=self._factory).get_dashboard_summary(limit=20)
            positions_payload = PaperDashboardTruthService(connection_factory=self._factory).get_positions(limit=20)
            pnl_payload = PaperDashboardTruthService(connection_factory=self._factory).get_pnl(limit=20)
            record.paper_intents = intent_payload
            record.no_trade = no_trade_payload
            record.paper_execution = execution_payload
            record.positions = positions_payload
            record.paper_pnl = pnl_payload
            record.blockers = list(execution_payload.get("top_block_reasons") or [])
            record.latest_paper_order = _latest_paper_order(self._factory)
            record.latest_paper_fill = _latest_paper_fill(self._factory)
            rows = positions_payload.get("positions") if isinstance(positions_payload, dict) else []
            record.latest_paper_position = rows[0] if isinstance(rows, list) and rows else None
        except Exception as exc:
            record.warnings = _unique([*record.warnings, f"Paper truth summary partial: {type(exc).__name__}: {exc}"])


def _latest_paper_order(factory: DatabaseConnectionFactory) -> dict[str, Any] | None:
    return _latest_row(factory, "paper_orders", "created_at")


def _latest_paper_fill(factory: DatabaseConnectionFactory) -> dict[str, Any] | None:
    return _latest_row(factory, "paper_fills", "created_at")


def _latest_row(factory: DatabaseConnectionFactory, table: str, order_column: str) -> dict[str, Any] | None:
    if not factory.enabled:
        return None
    with factory.connect() as conn:
        exists = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
        if not exists or not exists["table_name"]:
            return None
        row = conn.execute(f"SELECT * FROM {table} ORDER BY {order_column} DESC NULLS LAST, id DESC LIMIT 1").fetchone()
        return _json_safe(dict(row)) if row else None


def _validate_operator(actor: str, reason: str) -> list[str]:
    errors: list[str] = []
    if not actor.strip():
        errors.append("actor is required")
    if not reason.strip():
        errors.append("reason is required")
    return errors


def _json_safe(value: Any) -> Any:
    return json_safe(value)
