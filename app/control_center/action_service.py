from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.control_center.action_contract import (
    ControlCenterActionEnvelope,
    ControlCenterActionRequest,
    ControlCenterSafetyCheck,
    action_timestamp,
)
from app.control_center.full_monitor_run import FullMonitorRunRequest, FullMonitorStopRequest
from app.control_center.full_monitor_run_service import FullMonitorRunService
from app.control_center.paper_simulation import PaperSimulationActionRequest, PaperSimulationControlService
from app.control_center.runtime_supervisor import RuntimeSupervisorService, RuntimeSupervisorStartRequest, RuntimeSupervisorStopRequest
from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository
from app.runtime.runtime_errors import RuntimeModeTransitionDenied, RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor
from app.runtime.modes import RuntimeMode
from app.services.system_power import SystemPowerService
from app.stage4 import get_stage4_settings


ACTIVE_ACTIONS = {"system-on", "system-off", "kill-switch", "enable-paper-simulation", "disable-paper-simulation"}
KNOWN_ACTIONS = ACTIVE_ACTIONS | {"start-full-monitor-run", "stop-current-run", "reset-paper-balance"}


class ControlCenterActionService:
    def __init__(
        self,
        *,
        governor: StateGovernor | None = None,
        system_power: SystemPowerService | None = None,
        full_monitor_run: FullMonitorRunService | None = None,
        runtime_supervisor: RuntimeSupervisorService | None = None,
        paper_simulation: PaperSimulationControlService | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._governor = governor or StateGovernor()
        self._system_power = system_power or SystemPowerService()
        self._full_monitor_run = full_monitor_run or FullMonitorRunService(governor=self._governor)
        self._runtime_supervisor = runtime_supervisor or RuntimeSupervisorService(governor=self._governor)
        self._paper_simulation = paper_simulation or PaperSimulationControlService(governor=self._governor)
        self._connection_factory = connection_factory or DatabaseConnectionFactory()
        self._runtime_cycles = RuntimeCycleRepository()

    def execute(self, action_name: str, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        action = action_name.strip().lower()
        if action not in KNOWN_ACTIONS:
            return self._envelope(
                action=action_name,
                status="NOT_IMPLEMENTED",
                payload=payload,
                errors=[f"Unknown Control Center action: {action_name}"],
            )

        validation_errors = self._validate_operator_fields(payload)
        if validation_errors:
            return self._envelope(action=action, status="REJECTED", payload=payload, errors=validation_errors)

        if action == "kill-switch" and (payload.confirmation or "").strip() != "KILL":
            return self._envelope(
                action=action,
                status="REJECTED",
                payload=payload,
                safety_checks=[
                    self._check("explicit_confirmation", "FAIL", "KILL SWITCH requires confirmation text KILL.")
                ],
                errors=["KILL SWITCH requires confirmation text KILL."],
            )

        if action == "reset-paper-balance":
            if (payload.confirmation or "").strip() != "RESET PAPER BALANCE":
                return self._envelope(
                    action=action,
                    status="REJECTED",
                    payload=payload,
                    safety_checks=[
                        self._check(
                            "explicit_confirmation",
                            "FAIL",
                            "RESET PAPER BALANCE requires confirmation text RESET PAPER BALANCE.",
                        )
                    ],
                    errors=["RESET PAPER BALANCE requires confirmation text RESET PAPER BALANCE."],
                )
            return self._locked(
                action,
                payload,
                reason="No safe paper-only balance reset contract with audit persistence and ledger preservation was found.",
            )

        if action == "start-full-monitor-run":
            return self._start_full_monitor_run(payload)

        if action == "stop-current-run":
            return self._stop_full_monitor_run(payload)

        if action in {"system-on", "system-off"}:
            return self._system_power_action(action, payload)

        if action in {"enable-paper-simulation", "disable-paper-simulation"}:
            return self._paper_simulation_action(action, payload)

        if action == "kill-switch":
            return self._kill_switch(payload)

        return self._envelope(action=action, status="NOT_IMPLEMENTED", payload=payload)

    def _start_full_monitor_run(self, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        if payload.duration_minutes is None:
            return self._envelope(
                action="start-full-monitor-run",
                status="REJECTED",
                payload=payload,
                safety_checks=[self._check("duration_required", "FAIL", "duration_minutes is required.")],
                errors=["duration_minutes is required"],
            )
        if payload.interval_seconds is None:
            return self._envelope(
                action="start-full-monitor-run",
                status="REJECTED",
                payload=payload,
                safety_checks=[self._check("interval_required", "FAIL", "interval_seconds is required.")],
                errors=["interval_seconds is required"],
            )
        run = self._full_monitor_run.start(
            FullMonitorRunRequest(
                actor=payload.actor,
                reason=payload.reason,
                duration_minutes=payload.duration_minutes,
                interval_seconds=payload.interval_seconds,
                max_cycles=payload.max_cycles or 1,
            )
        )
        action_status = "ACCEPTED" if run.status in {"STARTING", "RUNNING", "COMPLETED", "STOPPED"} else run.status
        return self._envelope(
            action="start-full-monitor-run",
            status=action_status,
            payload=payload,
            audit_id=run.audit_id if action_status == "ACCEPTED" else None,
            safety_checks=[
                self._check("actor_required", "PASS", "Actor supplied."),
                self._check("reason_required", "PASS", "Reason supplied."),
                self._check("duration_required", "PASS", "Duration supplied and bounded to 1..60 minutes."),
                self._check("interval_required", "PASS", "Interval supplied and bounded to 10..300 seconds."),
                self._check("state_governor_checked", "PASS" if run.status in {"STARTING", "COMPLETED", "RUNNING"} else "FAIL", "Full Monitor Run service checked State Governor before start."),
                self._check("no_live_execution", "PASS", "Full Monitor Run does not call live execution."),
                self._check("unsafe_modules_skipped", "PASS", "Modules without safe monitor paths are marked SKIPPED."),
            ],
            result=run.to_action_result(),
            warnings=run.warnings,
            errors=run.errors,
        )

    def _stop_full_monitor_run(self, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        run = self._full_monitor_run.stop(FullMonitorStopRequest(actor=payload.actor, reason=payload.reason))
        action_status = "ACCEPTED" if run.status in {"STOPPED", "STOPPING"} else run.status
        return self._envelope(
            action="stop-current-run",
            status=action_status,
            payload=payload,
            audit_id=run.audit_id if action_status == "ACCEPTED" else None,
            safety_checks=[
                self._check("actor_required", "PASS" if payload.actor.strip() else "FAIL", "Actor is required."),
                self._check("reason_required", "PASS" if payload.reason.strip() else "FAIL", "Reason is required."),
                self._check("stop_safe", "PASS" if action_status == "ACCEPTED" else "FAIL", "Stop is safe even when no active run exists."),
                self._check("no_destructive_stop", "PASS", "Stop does not kill DB or services."),
            ],
            result=run.to_action_result(),
            warnings=run.warnings,
            errors=run.errors,
        )

    def _system_power_action(self, action: str, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        state_before, permissions_before, state_error = self._state_snapshot()
        if state_error:
            return self._locked(action, payload, reason=state_error, state_before=state_before)

        live_guard = self._live_safety_check()
        checks = [
            self._check("actor_required", "PASS", "Actor supplied."),
            self._check("reason_required", "PASS", "Reason supplied."),
            self._check("state_governor_loaded", "PASS", "Current runtime state and permissions loaded."),
            live_guard,
            self._check("no_order_creation", "PASS", "System power action does not create orders, fills, or positions."),
        ]
        if live_guard.status != "PASS":
            return self._locked(
                action,
                payload,
                reason=live_guard.detail,
                state_before=state_before,
                safety_checks=checks,
            )

        correlation_id = f"control_center_{action}_{uuid4().hex}"
        try:
            mode_result: dict[str, Any] | None = None
            supervisor_result: dict[str, Any] | None = None
            if action == "system-on":
                mode_result = self._ensure_safe_monitoring_mode(
                    payload=payload,
                    state_before=state_before,
                    correlation_id=correlation_id,
                )
            if action == "system-on":
                result = self._system_power.turn_on(actor=payload.actor, reason=payload.reason, correlation_id=correlation_id)
                supervisor = self._runtime_supervisor.start(
                    RuntimeSupervisorStartRequest(
                        actor=payload.actor,
                        reason=payload.reason,
                        interval_seconds=payload.interval_seconds,
                    )
                )
                supervisor_result = supervisor.to_action_result()
            else:
                paper_control = self._paper_simulation.force_disable_for_stop(
                    actor=payload.actor,
                    reason=f"SYSTEM OFF disables paper simulation: {payload.reason}",
                )
                supervisor = self._runtime_supervisor.stop(
                    RuntimeSupervisorStopRequest(actor=payload.actor, reason=payload.reason)
                )
                supervisor_result = supervisor.to_action_result()
                cycle_cleanup = self._close_open_runtime_cycles_for_system_off(payload.reason)
                result = self._system_power.turn_off(actor=payload.actor, reason=payload.reason, correlation_id=correlation_id)
        except ValueError as exc:
            return self._envelope(action=action, status="REJECTED", payload=payload, state_before=state_before, safety_checks=checks, errors=[str(exc)])
        except RuntimeModeTransitionDenied as exc:
            return self._locked(
                action,
                payload,
                reason=str(exc),
                state_before={"state": state_before, "permissions": permissions_before},
                safety_checks=checks + [self._check("safe_monitoring_mode", "LOCKED", str(exc))],
            )
        except Exception as exc:
            return self._envelope(action=action, status="ERROR", payload=payload, state_before=state_before, safety_checks=checks, errors=[str(exc)])

        state_after, permissions_after, _ = self._state_snapshot()
        result = {
            **result,
            "safe_monitoring_mode": mode_result,
            "supervisor": supervisor_result,
            "monitoring_enabled": bool(supervisor_result and supervisor_result.get("supervisor_status") in {"STARTING", "RUNNING", "DEGRADED"}),
            "paper_simulation": paper_control.to_action_result() if action == "system-off" else self._paper_simulation.status_record(include_paper_truth=False).to_action_result(),
            "runtime_cycle_cleanup": cycle_cleanup if action == "system-off" else {},
            "execution_enabled": False,
            "paper_execution_enabled": bool(action == "system-on" and self._paper_simulation.is_enabled()),
        }
        return self._envelope(
            action=action,
            status="ACCEPTED",
            payload=payload,
            audit_id=str(result.get("transition_id") or f"system_power_transitions:{correlation_id}"),
            state_before={"state": state_before, "permissions": permissions_before},
            state_after={"state": state_after, "permissions": permissions_after},
            safety_checks=checks
            + [
                self._check(
                    "safe_monitoring_mode",
                    "PASS" if action == "system-on" else "PASS",
                    "SYSTEM ON ensures DATA_ONLY monitoring mode before allowing runtime work."
                    if action == "system-on"
                    else "SYSTEM OFF does not alter runtime mode.",
                ),
                self._check(
                    "runtime_supervisor",
                    "PASS" if supervisor_result and supervisor_result.get("supervisor_status") in {"STARTING", "RUNNING", "DEGRADED", "STOPPING", "STOPPED"} else "LOCKED",
                    "SYSTEM ON starts the DATA_ONLY runtime supervisor."
                    if action == "system-on"
                    else "SYSTEM OFF requests the runtime supervisor to stop.",
                ),
                self._check("audit_recorded", "PASS", "System power transition and system_state_history audit were recorded."),
            ],
            result=result,
            warnings=[
                "System power actions do not enable live trading.",
                "SYSTEM OFF disables paper simulation as a safety reset.",
            ],
        )

    def _paper_simulation_action(self, action: str, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        state_before, permissions_before, state_error = self._state_snapshot()
        if state_error:
            return self._locked(action, payload, reason=state_error, state_before=state_before)
        live_guard = self._live_safety_check()
        checks = [
            self._check("actor_required", "PASS", "Actor supplied."),
            self._check("reason_required", "PASS", "Reason supplied."),
            self._check("state_governor_loaded", "PASS", "Current runtime state and permissions loaded."),
            live_guard,
            self._check("paper_only", "PASS", "Paper simulation creates only paper/simulated artifacts."),
            self._check("no_live_execution", "PASS", "Paper simulation action does not call live execution APIs."),
        ]
        if live_guard.status != "PASS":
            return self._locked(action, payload, reason=live_guard.detail, state_before=state_before, safety_checks=checks)
        if action == "enable-paper-simulation":
            record = self._paper_simulation.enable(PaperSimulationActionRequest(actor=payload.actor, reason=payload.reason))
            action_status = "ACCEPTED" if record.status == "ENABLED" else record.status
        else:
            record = self._paper_simulation.disable(PaperSimulationActionRequest(actor=payload.actor, reason=payload.reason))
            action_status = "ACCEPTED" if record.status == "DISABLED" else record.status
        state_after, permissions_after, _ = self._state_snapshot()
        return self._envelope(
            action=action,
            status=action_status,
            payload=payload,
            audit_id=f"system_state_history:{action}:{record.last_changed_at or action_timestamp()}",
            state_before={"state": state_before, "permissions": permissions_before},
            state_after={"state": state_after, "permissions": permissions_after},
            safety_checks=checks
            + [
                self._check(
                    "paper_simulation_control",
                    "PASS" if action_status == "ACCEPTED" else "LOCKED",
                    "Paper simulation state is explicit and visible in Control Center.",
                ),
                self._check("state_governor_not_bypassed", "PASS", "Control persisted through State Governor/system_state audit path."),
            ],
            result={
                "paper_simulation": record.to_action_result(),
                "paper_execution_enabled": bool(record.enabled),
                "execution_enabled": False,
                "live_execution_enabled": False,
            },
            warnings=record.warnings,
            errors=record.errors,
        )

    def _ensure_safe_monitoring_mode(
        self,
        *,
        payload: ControlCenterActionRequest,
        state_before: dict[str, Any],
        correlation_id: str,
    ) -> dict[str, Any]:
        current_mode = str(state_before.get("current_mode") or "").upper()
        kill_active = bool(state_before.get("kill_switch_active"))
        if current_mode == RuntimeMode.KILL.value or kill_active:
            raise RuntimeModeTransitionDenied("KILL is active; SYSTEM ON cannot resume from KILL. Use the explicit runtime resume path after operator review.")
        requested_mode = str(
            payload.metadata.get("requested_execution_mode")
            or payload.metadata.get("execution_mode")
            or RuntimeMode.DATA_ONLY.value
        ).strip().upper()
        target_mode = RuntimeMode.PAPER if requested_mode == RuntimeMode.PAPER.value else RuntimeMode.DATA_ONLY
        if current_mode == target_mode.value:
            return {"from_mode": current_mode, "to_mode": target_mode.value, "changed": False}

        state = self._governor.request_mode_change(
            target_mode,
            actor=payload.actor,
            reason=f"Control Center SYSTEM ON {target_mode.value} runtime mode: {payload.reason}",
            metadata={
                **payload.metadata,
                "control_center_action": "system-on",
                "execution_mode": target_mode.value,
                "paper_is_execution_adapter_only": target_mode == RuntimeMode.PAPER,
                "live_adapter_enabled": False,
                "non_trading_event": target_mode == RuntimeMode.DATA_ONLY,
            },
            correlation_id=correlation_id,
            action="CONTROL_CENTER_SYSTEM_ON_RUNTIME_MODE",
        )
        return {"from_mode": current_mode or None, "to_mode": state.current_mode.value, "changed": True}

    def _close_open_runtime_cycles_for_system_off(self, reason: str) -> dict[str, Any]:
        if not self._connection_factory.enabled:
            return {"status": "SKIPPED", "reason": "DATABASE_UNAVAILABLE"}
        try:
            with self._connection_factory.connect() as conn, conn.transaction():
                stopped = self._runtime_cycles.mark_open_cycles_safe_stopped(
                    conn,
                    reason=f"SYSTEM_OFF: {reason}",
                )
            return {"status": "OK", "safe_stopped_cycles": stopped}
        except Exception as exc:
            return {"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"}

    def _kill_switch(self, payload: ControlCenterActionRequest) -> ControlCenterActionEnvelope:
        state_before, permissions_before, state_error = self._state_snapshot()
        if state_error:
            return self._locked("kill-switch", payload, reason=state_error, state_before=state_before)

        checks = [
            self._check("actor_required", "PASS", "Actor supplied."),
            self._check("reason_required", "PASS", "Reason supplied."),
            self._check("explicit_confirmation", "PASS", "KILL confirmation supplied."),
            self._check("state_governor_loaded", "PASS", "Current runtime state and permissions loaded."),
            self._check("no_order_creation", "PASS", "KILL action does not create orders, fills, or positions."),
        ]
        correlation_id = f"control_center_kill_{uuid4().hex}"
        try:
            supervisor = self._runtime_supervisor.mark_killed(actor=payload.actor, reason=payload.reason)
            paper_control = self._paper_simulation.force_disable_for_stop(
                actor=payload.actor,
                reason=f"KILL disables paper simulation: {payload.reason}",
            )
            state = self._governor.activate_kill(
                actor=payload.actor,
                reason=payload.reason,
                correlation_id=correlation_id,
                metadata={**payload.metadata, "control_center_action": "kill-switch", "non_trading_event": True},
            )
        except RuntimeModeTransitionDenied as exc:
            return self._envelope(
                action="kill-switch",
                status="REJECTED",
                payload=payload,
                state_before={"state": state_before, "permissions": permissions_before},
                safety_checks=checks + [self._check("state_governor_transition", "FAIL", str(exc))],
                errors=[str(exc)],
            )
        except Exception as exc:
            return self._envelope(
                action="kill-switch",
                status="ERROR",
                payload=payload,
                state_before={"state": state_before, "permissions": permissions_before},
                safety_checks=checks,
                errors=[str(exc)],
            )

        state_after = state.to_dict()
        permissions_after = self._safe_permissions()
        return self._envelope(
            action="kill-switch",
            status="ACCEPTED",
            payload=payload,
            audit_id=f"system_state_history:{correlation_id}",
            state_before={"state": state_before, "permissions": permissions_before},
            state_after={"state": state_after, "permissions": permissions_after},
            safety_checks=checks
            + [
                self._check("state_governor_transition", "PASS", "State Governor accepted KILL transition."),
                self._check("audit_recorded", "PASS", "system_state_history audit was recorded."),
            ],
            result={
                "current_mode": state.current_mode.value,
                "kill_switch_active": state.kill_switch_active,
                "supervisor": supervisor.to_action_result(),
                "paper_simulation": paper_control.to_action_result(),
                "execution_enabled": False,
                "paper_execution_enabled": False,
            },
            warnings=["KILL blocks trading behavior through the State Governor permission model."],
        )

    def _validate_operator_fields(self, payload: ControlCenterActionRequest) -> list[str]:
        errors: list[str] = []
        if not payload.actor.strip():
            errors.append("actor is required")
        if not payload.reason.strip():
            errors.append("reason is required")
        return errors

    def _state_snapshot(self) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        try:
            state = self._governor.get_current_state().to_dict()
            permissions = self._governor.get_permissions().to_dict()
            return state, permissions, None
        except RuntimeStateUnavailable as exc:
            return {}, {}, f"State Governor unavailable: {exc}"
        except Exception as exc:
            return {}, {}, f"State Governor check failed: {exc}"

    def _safe_permissions(self) -> dict[str, Any]:
        try:
            return self._governor.get_permissions().to_dict()
        except Exception:
            return {}

    def _live_safety_check(self) -> ControlCenterSafetyCheck:
        try:
            stage4 = get_stage4_settings()
        except Exception as exc:
            return self._check("live_trading_disabled", "FAIL", f"Live safety settings could not be loaded: {exc}")
        if bool(stage4.live_trading_enabled):
            return self._check("live_trading_disabled", "FAIL", "LIVE_TRADING_ENABLED is true; Control Center power actions are locked.")
        return self._check("live_trading_disabled", "PASS", "LIVE_TRADING_ENABLED is false.")

    def _locked(
        self,
        action: str,
        payload: ControlCenterActionRequest,
        *,
        reason: str,
        state_before: dict[str, Any] | None = None,
        safety_checks: list[ControlCenterSafetyCheck] | None = None,
    ) -> ControlCenterActionEnvelope:
        return self._envelope(
            action=action,
            status="LOCKED",
            payload=payload,
            state_before=state_before or {},
            safety_checks=safety_checks
            or [self._check("safe_backend_contract", "LOCKED", reason), self._check("no_order_creation", "PASS", "No execution artifacts are created.")],
            warnings=[reason],
        )

    def _not_implemented(self, action: str, payload: ControlCenterActionRequest, *, reason: str) -> ControlCenterActionEnvelope:
        return self._envelope(
            action=action,
            status="NOT_IMPLEMENTED",
            payload=payload,
            safety_checks=[
                self._check("safe_backend_contract", "NOT_IMPLEMENTED", reason),
                self._check("no_order_creation", "PASS", "No execution artifacts are created."),
            ],
            warnings=[reason],
        )

    def _envelope(
        self,
        *,
        action: str,
        status: str,
        payload: ControlCenterActionRequest,
        audit_id: str | None = None,
        state_before: dict[str, Any] | None = None,
        state_after: dict[str, Any] | None = None,
        safety_checks: list[ControlCenterSafetyCheck] | None = None,
        result: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> ControlCenterActionEnvelope:
        return ControlCenterActionEnvelope(
            action=action,
            status=status,  # type: ignore[arg-type]
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            timestamp=action_timestamp(),
            audit_id=audit_id,
            state_before=state_before or {},
            state_after=state_after or {},
            safety_checks=safety_checks or [],
            result=result or {},
            warnings=warnings or [],
            errors=errors or [],
        )

    @staticmethod
    def _check(name: str, status: str, detail: str) -> ControlCenterSafetyCheck:
        return ControlCenterSafetyCheck(name=name, status=status, detail=detail)  # type: ignore[arg-type]
