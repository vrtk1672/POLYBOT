from __future__ import annotations

import asyncio
import inspect
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.control_center.full_monitor_run import FullMonitorModuleResult, utc_now_iso
from app.control_center.full_monitor_run_service import (
    SAFE_ENVELOPE_MODULES,
    SKIPPED_MODULES,
    _counter,
    _extract_counters,
    _json_dumps,
    _unique,
)
from app.control_center.paper_simulation import PaperSimulationControlService
from app.control_center.query_service import ControlCenterQueryService
from app.control_center.truth_contract import truth_envelope
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.runtime.cycle_orchestrator import RuntimeCycleOrchestrator
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.runtime_errors import RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor
from app.services.paper_execution import PaperExecutionService
from app.services.paper_exit_loop import PaperExitLoopService
from app.services.paper_intents import PaperIntentGateService
from app.stage4 import get_stage4_settings


RuntimeSupervisorStatus = Literal[
    "IDLE",
    "STARTING",
    "RUNNING",
    "STOPPING",
    "STOPPED",
    "DEGRADED",
    "ERROR",
    "KILLED",
    "LOCKED",
    "REJECTED",
]


class RuntimeSupervisorStartRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")
    interval_seconds: int | None = None


class RuntimeSupervisorStopRequest(BaseModel):
    actor: str = Field(default="")
    reason: str = Field(default="")
    status: RuntimeSupervisorStatus = "STOPPED"


class RuntimeSupervisorRecord(BaseModel):
    supervisor_available: bool = True
    supervisor_status: RuntimeSupervisorStatus
    session_id: str | None = None
    system_power: str = "UNKNOWN"
    mode: str = "UNKNOWN"
    interval_seconds: int = 60
    started_at: str | None = None
    updated_at: str | None = None
    stopped_at: str | None = None
    last_cycle_at: str | None = None
    next_cycle_at: str | None = None
    elapsed_seconds: float = 0.0
    cycles_completed: int = 0
    cycles_failed: int = 0
    current_cycle_status: str = "IDLE"
    last_cycle_summary: dict[str, Any] = Field(default_factory=dict)
    markets_checked: int = 0
    events_seen: int = 0
    opportunities_found: int = 0
    no_trades_logged: int = 0
    ai_calls: int = 0
    ai_failures: int = 0
    paper_orders: int = 0
    paper_fills: int = 0
    positions_updated: int = 0
    paper_simulation_enabled: bool = False
    paper_simulation_status: str = "DISABLED"
    paper_intents_created: int = 0
    paper_intents_blocked: int = 0
    paper_orders_created: int = 0
    paper_fills_created: int = 0
    paper_positions_opened: int = 0
    paper_positions_marked: int = 0
    paper_pnl: dict[str, Any] = Field(default_factory=dict)
    paper_blockers: list[str] = Field(default_factory=list)
    latest_paper_flow: dict[str, Any] = Field(default_factory=dict)
    source_refresh_orchestrator_state: str = "NOT_CONFIGURED"
    source_refresh_cycles_completed: int = 0
    sources_refreshed_this_cycle: int = 0
    sources_failed_this_cycle: int = 0
    sources_no_new_data_this_cycle: int = 0
    derived_signals_created_this_cycle: int = 0
    latest_source_refresh_at: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    execution_enabled: bool = False
    paper_execution_enabled: bool = False
    report_path: str | None = None
    report_json_path: str | None = None
    actor: str = ""
    reason: str = ""

    def to_action_result(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class RuntimeSupervisorStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._record: RuntimeSupervisorRecord | None = None
        self._stop_event: Event | None = None

    def get(self) -> RuntimeSupervisorRecord | None:
        with self._lock:
            return deepcopy(self._record)

    def set(self, record: RuntimeSupervisorRecord) -> None:
        with self._lock:
            self._record = deepcopy(record)

    def register_stop_event(self, event: Event) -> None:
        with self._lock:
            self._stop_event = event

    def stop_event(self) -> Event | None:
        with self._lock:
            return self._stop_event

    def clear_stop_event(self) -> None:
        with self._lock:
            self._stop_event = None


DEFAULT_RUNTIME_SUPERVISOR_STORE = RuntimeSupervisorStore()


class RuntimeSupervisorService:
    def __init__(
        self,
        *,
        governor: StateGovernor | None = None,
        query_service: ControlCenterQueryService | None = None,
        store: RuntimeSupervisorStore | None = None,
        event_bus: EventBus | None = None,
        paper_simulation: PaperSimulationControlService | None = None,
        candidate_producer: Any | None = None,
        candidate_orderbook_refresher: Any | None = None,
        orderbook_refresher: Any | None = None,
        source_refresh_orchestrator: Any | None = None,
        paper_intents: PaperIntentGateService | None = None,
        paper_execution: PaperExecutionService | None = None,
        paper_exits: PaperExitLoopService | None = None,
        run_in_background: bool = True,
        report_dir: Path | str = "run_reports/control_center_supervisor_sessions",
        sleep_between_cycles: bool = True,
    ) -> None:
        self._governor = governor or StateGovernor()
        self._query_service = query_service or ControlCenterQueryService()
        self._store = store or DEFAULT_RUNTIME_SUPERVISOR_STORE
        self._event_bus = event_bus or EventBus()
        self._paper_simulation = paper_simulation or PaperSimulationControlService()
        self._candidate_producer = candidate_producer
        self._candidate_orderbook_refresher = candidate_orderbook_refresher
        self._orderbook_refresher = orderbook_refresher
        self._source_refresh_orchestrator = source_refresh_orchestrator
        self._paper_intents = paper_intents or PaperIntentGateService()
        self._paper_execution = paper_execution or PaperExecutionService()
        self._paper_exits = paper_exits or PaperExitLoopService()
        self._cycle_orchestrator = RuntimeCycleOrchestrator(governor=self._governor)
        self._run_in_background = run_in_background
        self._report_dir = Path(report_dir)
        self._sleep_between_cycles = sleep_between_cycles

    def start(self, payload: RuntimeSupervisorStartRequest) -> RuntimeSupervisorRecord:
        errors = _validate_operator(payload.actor, payload.reason)
        if errors:
            return self._rejected(payload, errors)
        interval_seconds = _bounded_interval(payload.interval_seconds)
        locked = self._start_lock_reason()
        if locked:
            return self._locked(payload, locked, interval_seconds=interval_seconds)

        active = self._store.get()
        if active and active.supervisor_status in {"STARTING", "RUNNING", "STOPPING", "DEGRADED"}:
            active.updated_at = utc_now_iso()
            active.warnings = _unique([*active.warnings, "Runtime supervisor already running; SYSTEM ON is idempotent."])
            self._store.set(active)
            return active

        state = self._safe_state()
        now = utc_now_iso()
        record = RuntimeSupervisorRecord(
            supervisor_status="STARTING",
            session_id=f"runtime_supervisor_{uuid4().hex}",
            system_power=str(getattr(getattr(state, "system_power", None), "value", getattr(state, "system_power", "UNKNOWN"))),
            mode=str(getattr(getattr(state, "current_mode", None), "value", getattr(state, "current_mode", "UNKNOWN"))),
            interval_seconds=interval_seconds,
            started_at=now,
            updated_at=now,
            next_cycle_at=now,
            current_cycle_status="STARTING",
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            warnings=[
                f"Stage 28 runtime supervisor starts in {str(getattr(getattr(state, 'current_mode', None), 'value', getattr(state, 'current_mode', 'UNKNOWN')))} mode.",
                "Live execution is disabled. PAPER mode routes only through the paper execution adapter.",
            ],
        )
        self._store.set(record)
        stop_event = Event()
        self._store.register_stop_event(stop_event)
        if self._run_in_background:
            Thread(target=self._run_loop_safe, args=(record, stop_event), name=f"polybot-supervisor-{record.session_id}", daemon=True).start()
            return self._store.get() or record
        self._run_one_cycle_for_test(record)
        return self._store.get() or record

    def stop(self, payload: RuntimeSupervisorStopRequest) -> RuntimeSupervisorRecord:
        errors = _validate_operator(payload.actor, payload.reason)
        if errors:
            return RuntimeSupervisorRecord(
                supervisor_status="REJECTED",
                updated_at=utc_now_iso(),
                actor=payload.actor.strip(),
                reason=payload.reason.strip(),
                errors=errors,
            )
        active = self._store.get()
        if active is None:
            record = RuntimeSupervisorRecord(
                supervisor_status=payload.status,
                updated_at=utc_now_iso(),
                stopped_at=utc_now_iso(),
                actor=payload.actor.strip(),
                reason=payload.reason.strip(),
                warnings=["No active runtime supervisor exists. Stop request recorded as safe no-op."],
            )
            self._store.set(record)
            return record

        now = utc_now_iso()
        active.supervisor_status = "STOPPING"
        active.current_cycle_status = "STOPPING"
        active.updated_at = now
        active.warnings = _unique([*active.warnings, f"Stop requested by {payload.actor.strip()}: {payload.reason.strip()}"])
        stop_event = self._store.stop_event()
        if stop_event:
            stop_event.set()
            if active.current_cycle_status != "RUNNING":
                active = self._finish(active, payload.status)
        else:
            active = self._finish(active, payload.status)
        self._store.set(active)
        return active

    def mark_killed(self, *, actor: str, reason: str) -> RuntimeSupervisorRecord:
        return self.stop(RuntimeSupervisorStopRequest(actor=actor, reason=reason, status="KILLED"))

    def status(self) -> dict[str, Any]:
        record = self._store.get()
        if record is None:
            record = RuntimeSupervisorRecord(supervisor_status="IDLE", updated_at=utc_now_iso())
        try:
            state = self._governor.get_current_state()
            record.mode = state.current_mode.value
            record.system_power = state.system_power.value
            if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
                record.supervisor_status = "KILLED"
            if record.system_power == "OFF" or record.supervisor_status in {"IDLE", "STOPPED", "KILLED", "LOCKED", "REJECTED"}:
                record.paper_simulation_enabled = False
                record.paper_simulation_status = "DISABLED"
                record.paper_execution_enabled = False
        except Exception as exc:
            record.warnings = _unique([*record.warnings, f"State Governor status unavailable: {exc}"])

        status = "REAL" if record.supervisor_status in {"RUNNING", "STOPPED", "KILLED"} else "PARTIAL"
        truth_state = "ACTIVE_FRESH" if record.supervisor_status == "RUNNING" else "LAST_KNOWN"
        if record.supervisor_status in {"ERROR", "DEGRADED"}:
            status = "ERROR" if record.supervisor_status == "ERROR" else "PARTIAL"
            truth_state = "REFRESH_REQUIRED"
        if record.supervisor_status == "IDLE":
            status = "MISSING"
            truth_state = "UNKNOWN"
            record.warnings = _unique([*record.warnings, "Runtime supervisor has not been started in this process."])
        return truth_envelope(
            status=status,
            source="control_center:runtime_supervisor",
            truth_state=truth_state,
            data=record.to_action_result(),
            last_updated=record.updated_at or record.started_at or datetime.now(UTC),
            stale_after_seconds=300,
            warnings=record.warnings,
            errors=record.errors,
        ).to_dict()

    def _run_loop_safe(self, record: RuntimeSupervisorRecord, stop_event: Event) -> None:
        try:
            self._run_loop(record, stop_event)
        finally:
            self._store.clear_stop_event()

    def _run_loop(self, record: RuntimeSupervisorRecord, stop_event: Event) -> None:
        start_monotonic = monotonic()
        record.supervisor_status = "RUNNING"
        record.current_cycle_status = "IDLE"
        record.updated_at = utc_now_iso()
        self._store.set(record)
        self._publish_event(EventType.RUNTIME_CYCLE_STARTED.value, record, {"supervisor_session_id": record.session_id, "status": "STARTED"})

        while not stop_event.is_set():
            cycle_started = monotonic()
            record = self._store.get() or record
            state = self._safe_state()
            if state is not None:
                record.mode = str(getattr(getattr(state, "current_mode", None), "value", getattr(state, "current_mode", "UNKNOWN")))
                record.system_power = str(getattr(getattr(state, "system_power", None), "value", getattr(state, "system_power", "UNKNOWN")))
            if self._stop_reason():
                record.supervisor_status = "KILLED" if record.mode == RuntimeMode.KILL.value else "STOPPED"
                record.warnings = _unique([*record.warnings, "Runtime supervisor stopped because State Governor no longer allows safe collection/PAPER runtime work."])
                break
            record.current_cycle_status = "RUNNING"
            record.updated_at = utc_now_iso()
            self._store.set(record)
            v2_cycle_id = self._cycle_orchestrator.start_cycle(
                metadata={
                    "source": "runtime_supervisor",
                    "supervisor_session_id": record.session_id,
                    "runtime_mode": record.mode,
                    "paper_simulation_enabled": False,
                    "paper_execution_enabled": False,
                }
            )
            try:
                module_results = self._execute_cycle()
                paper_flow = self._execute_paper_cycle(record)
                self._apply_cycle(record, module_results, paper_flow)
                record.cycles_completed += 1
                record.current_cycle_status = "COMPLETED"
                record.last_cycle_at = utc_now_iso()
                record.supervisor_status = "RUNNING" if not record.errors else "DEGRADED"
                record.last_cycle_summary = _cycle_summary(module_results, paper_flow)
                self._cycle_orchestrator.finish_cycle(
                    status="COMPLETED" if not record.errors else "DEGRADED",
                    error_count=len(record.errors),
                    warning_count=len(record.warnings),
                    metadata={
                        "source": "runtime_supervisor",
                        "supervisor_session_id": record.session_id,
                        "runtime_mode": record.mode,
                        "paper_simulation_enabled": bool(paper_flow.get("enabled")),
                        "paper_execution_enabled": bool(paper_flow.get("paper_execution_enabled")),
                        "candidate_producer": _module_counters(module_results, "candidate_producer"),
                        "candidate_orderbook_refresher": _module_counters(module_results, "candidate_orderbook_refresher"),
                        "orderbook_refresher": _module_counters(module_results, "orderbook_refresher"),
                        "source_refresh_orchestrator": _module_counters(module_results, "source_refresh_orchestrator"),
                        "paper_flow": paper_flow,
                    },
                )
            except Exception as exc:
                record.cycles_failed += 1
                record.current_cycle_status = "ERROR"
                record.supervisor_status = "DEGRADED"
                record.errors = _unique([*record.errors, f"{type(exc).__name__}: {exc}"])
                self._cycle_orchestrator.finish_cycle(
                    status="FAILED",
                    error_count=1,
                    warning_count=len(record.warnings),
                    metadata={
                        "source": "runtime_supervisor",
                        "supervisor_session_id": record.session_id,
                        "cycle_id": v2_cycle_id,
                        "error": str(exc),
                    },
                )
            record.elapsed_seconds = max(0.0, monotonic() - start_monotonic)
            wait_seconds = max(0.0, record.interval_seconds - (monotonic() - cycle_started))
            record.next_cycle_at = datetime.fromtimestamp(datetime.now(UTC).timestamp() + wait_seconds, UTC).isoformat()
            record.updated_at = utc_now_iso()
            self._store.set(record)
            self._publish_event(EventType.RUNTIME_CYCLE_FINISHED.value, record, {"supervisor_session_id": record.session_id, "status": record.current_cycle_status})
            if not self._sleep_between_cycles:
                return
            if stop_event.wait(wait_seconds):
                break

        latest = self._store.get() or record
        self._finish(latest, "STOPPED" if latest.supervisor_status not in {"KILLED", "ERROR"} else latest.supervisor_status)

    def _run_one_cycle_for_test(self, record: RuntimeSupervisorRecord) -> None:
        event = Event()
        self._run_loop(record, event)

    def _execute_cycle(self) -> list[FullMonitorModuleResult]:
        module_results: list[FullMonitorModuleResult] = []
        for module, behavior, getter in SAFE_ENVELOPE_MODULES:
            module_results.append(self._run_read_only_module(module, behavior, getter))
        module_results.append(self._run_candidate_producer_module())
        module_results.append(self._run_candidate_orderbook_refresher_module())
        module_results.append(self._run_orderbook_refresher_module())
        module_results.append(self._run_source_refresh_orchestrator_module())
        for module, reason in SKIPPED_MODULES:
            module_results.append(FullMonitorModuleResult(module=module, status="SKIPPED", behavior=reason, warnings=[reason]))
        return module_results

    def _run_candidate_producer_module(self) -> FullMonitorModuleResult:
        behavior = "Safe candidate producer refresh through PaperEligibilityService only; no intents, orders, fills, or positions."
        if self._candidate_producer is None:
            return FullMonitorModuleResult(
                module="candidate_producer",
                status="SKIPPED",
                behavior=behavior,
                source="not_configured",
                warnings=["CANDIDATE_PRODUCER_NOT_CONFIGURED"],
            )
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            return FullMonitorModuleResult(
                module="candidate_producer",
                status="SKIPPED",
                behavior=behavior,
                source="StateGovernor",
                warnings=["CANDIDATES_BLOCKED_BY_RUNTIME"],
            )
        try:
            if hasattr(self._candidate_producer, "evaluate_candidates"):
                result = self._candidate_producer.evaluate_candidates(limit=100, include_blocked=True, write_candidates=True)
            else:
                result = self._candidate_producer()
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
            data = result if isinstance(result, dict) else {}
            errors = [str(item) for item in data.get("errors", [])] if isinstance(data.get("errors"), list) else []
            safety_errors: list[str] = []
            for key in ("orders_created", "fills_created", "positions_created", "live_actions_created"):
                if _safe_int(data.get(key)) > 0:
                    safety_errors.append(f"UNEXPECTED_{key.upper()}:{data.get(key)}")
            candidates_changed = _safe_int(data.get("candidates_created")) + _safe_int(data.get("candidates_updated"))
            return FullMonitorModuleResult(
                module="candidate_producer",
                status="ERROR" if errors or safety_errors else "COMPLETED",
                behavior=behavior,
                source=self._candidate_producer.__class__.__name__,
                counters={
                    "exit_plans_checked": _safe_int(data.get("exit_plans_checked")),
                    "candidates_created": _safe_int(data.get("candidates_created")),
                    "candidates_updated": _safe_int(data.get("candidates_updated")),
                    "eligible_count": _safe_int(data.get("eligible_count")),
                    "blocked_count": _safe_int(data.get("blocked_count")),
                    "orders_created": _safe_int(data.get("orders_created")),
                    "fills_created": _safe_int(data.get("fills_created")),
                    "positions_created": _safe_int(data.get("positions_created")),
                    "live_actions_created": _safe_int(data.get("live_actions_created")),
                },
                warnings=[] if candidates_changed else ["CANDIDATES_NOT_UPDATED_WITH_REASON"],
                errors=[*errors, *safety_errors],
            )
        except Exception as exc:
            return FullMonitorModuleResult(
                module="candidate_producer",
                status="ERROR",
                behavior=behavior,
                source=self._candidate_producer.__class__.__name__,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    def _run_candidate_orderbook_refresher_module(self) -> FullMonitorModuleResult:
        behavior = "Bounded DATA_ONLY candidate-targeted trusted orderbook refresh; no intents, orders, fills, or positions."
        if self._candidate_orderbook_refresher is None:
            return FullMonitorModuleResult(
                module="candidate_orderbook_refresher",
                status="SKIPPED",
                behavior=behavior,
                source="not_configured",
                warnings=["CANDIDATE_TARGETED_REFRESH_NOT_WIRED"],
            )
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            return FullMonitorModuleResult(
                module="candidate_orderbook_refresher",
                status="SKIPPED",
                behavior=behavior,
                source="StateGovernor",
                warnings=["CANDIDATE_TARGETED_REFRESH_BLOCKED_BY_MODE"],
            )
        try:
            if hasattr(self._candidate_orderbook_refresher, "resolve"):
                result = self._candidate_orderbook_refresher.resolve(limit=20, refresh_orderbooks=True)
            else:
                result = self._candidate_orderbook_refresher()
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
            data = result if isinstance(result, dict) else {}
            errors = [str(item) for item in data.get("errors", [])] if isinstance(data.get("errors"), list) else []
            if data.get("error_message"):
                errors.append(str(data["error_message"]))
            safety_errors: list[str] = []
            paper_mode = self._current_mode_value() == RuntimeMode.PAPER.value
            for key in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "canonical_positions"):
                before = _safe_int((data.get("safety_counts_before") or {}).get(key)) if isinstance(data.get("safety_counts_before"), dict) else 0
                after = _safe_int((data.get("safety_counts_after") or {}).get(key)) if isinstance(data.get("safety_counts_after"), dict) else before
                if after > before and not _expected_paper_adapter_delta(key, paper_mode=paper_mode):
                    safety_errors.append(f"UNEXPECTED_{key.upper()}_DELTA:{after - before}")
            warnings: list[str] = []
            if _safe_int(data.get("trusted_matches_created")) <= 0 and _safe_int(data.get("trusted_matches_refreshed")) <= 0 and _safe_int(data.get("orderbook_snapshots_created")) <= 0:
                reasons = data.get("rejected_reason_counts") if isinstance(data.get("rejected_reason_counts"), list) else []
                warnings.extend(str(reason.get("reason")) for reason in reasons if isinstance(reason, dict) and reason.get("reason"))
                if not warnings:
                    warnings.append("CANDIDATE_TARGETED_REFRESH_NO_MATCHES")
            return FullMonitorModuleResult(
                module="candidate_orderbook_refresher",
                status="ERROR" if errors or safety_errors else "COMPLETED",
                behavior=behavior,
                source=self._candidate_orderbook_refresher.__class__.__name__,
                counters={
                    "candidates_checked": _safe_int(data.get("candidates_checked")),
                    "trusted_matches_created": _safe_int(data.get("trusted_matches_created")),
                    "trusted_matches_refreshed": _safe_int(data.get("trusted_matches_refreshed")),
                    "orderbook_snapshots_created": _safe_int(data.get("orderbook_snapshots_created")),
                    "missing_orderbook_count": _safe_int(data.get("missing_orderbook_count")),
                    "stale_count": _safe_int(data.get("stale_count")),
                    "token_mismatch_count": _safe_int(data.get("token_mismatch_count")),
                    "live_orders_delta": _safe_int(data.get("live_orders_delta")),
                    "real_orders_delta": _safe_int(data.get("real_orders_delta")),
                },
                warnings=_unique(warnings),
                errors=[*errors, *safety_errors],
            )
        except Exception as exc:
            return FullMonitorModuleResult(
                module="candidate_orderbook_refresher",
                status="ERROR",
                behavior=behavior,
                source=self._candidate_orderbook_refresher.__class__.__name__,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    def _run_orderbook_refresher_module(self) -> FullMonitorModuleResult:
        behavior = "Bounded DATA_ONLY orderbook refresh through existing read-only watcher; no intents, orders, fills, or positions."
        if self._orderbook_refresher is None:
            return FullMonitorModuleResult(
                module="orderbook_refresher",
                status="SKIPPED",
                behavior=behavior,
                source="not_configured",
                warnings=["ORDERBOOK_REFRESH_NOT_WIRED"],
            )
        if not self._governor.can_execute(RuntimeAction.RUN_INTELLIGENCE):
            return FullMonitorModuleResult(
                module="orderbook_refresher",
                status="SKIPPED",
                behavior=behavior,
                source="StateGovernor",
                warnings=["ORDERBOOK_REFRESH_BLOCKED_BY_MODE"],
            )
        try:
            if hasattr(self._orderbook_refresher, "run"):
                result = self._orderbook_refresher.run(limit=10, dry_run=False, max_seconds=20, include_priority=10)
            else:
                result = self._orderbook_refresher()
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
            data = result if isinstance(result, dict) else {}
            errors = [str(item) for item in data.get("errors", [])] if isinstance(data.get("errors"), list) else []
            if data.get("error_message"):
                errors.append(str(data["error_message"]))
            safety_errors: list[str] = []
            paper_mode = self._current_mode_value() == RuntimeMode.PAPER.value
            for key in ("paper_intents", "paper_orders", "paper_fills", "paper_positions", "live_orders", "orders_v2", "fills_v2", "canonical_positions"):
                before = _safe_int((data.get("safety_counts_before") or {}).get(key)) if isinstance(data.get("safety_counts_before"), dict) else 0
                after = _safe_int((data.get("safety_counts_after") or {}).get(key)) if isinstance(data.get("safety_counts_after"), dict) else before
                if after > before and not _expected_paper_adapter_delta(key, paper_mode=paper_mode):
                    safety_errors.append(f"UNEXPECTED_{key.upper()}_DELTA:{after - before}")
            warnings: list[str] = []
            if _safe_int(data.get("orderbooks_refreshed")) <= 0 and _safe_int(data.get("snapshots_created")) <= 0:
                blockers = data.get("blocker_counts") if isinstance(data.get("blocker_counts"), dict) else {}
                if blockers:
                    warnings.extend(str(key) for key in blockers.keys() if key != "OK")
                else:
                    warnings.append("ORDERBOOK_REFRESH_NOT_WIRED")
            return FullMonitorModuleResult(
                module="orderbook_refresher",
                status="ERROR" if errors or safety_errors else "COMPLETED",
                behavior=behavior,
                source=self._orderbook_refresher.__class__.__name__,
                counters={
                    "watch_items_checked": _safe_int(data.get("watch_items_checked")),
                    "orderbooks_refreshed": _safe_int(data.get("orderbooks_refreshed")),
                    "snapshots_created": _safe_int(data.get("snapshots_created")),
                    "events_published": _safe_int(data.get("events_published")),
                    "token_unavailable_count": _safe_int(data.get("token_unavailable_count")),
                    "market_resolved_count": _safe_int(data.get("market_resolved_count")),
                    "live_orders_delta": _safe_int(data.get("live_orders_delta")),
                    "real_orders_delta": _safe_int(data.get("real_orders_delta")),
                },
                warnings=_unique(warnings),
                errors=[*errors, *safety_errors],
            )
        except Exception as exc:
            return FullMonitorModuleResult(
                module="orderbook_refresher",
                status="ERROR",
                behavior=behavior,
                source=self._orderbook_refresher.__class__.__name__,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    def _run_source_refresh_orchestrator_module(self) -> FullMonitorModuleResult:
        behavior = "TTL-aware DATA_ONLY source refresh and derived signal production; no intents, orders, fills, positions, or capital mutations."
        if self._source_refresh_orchestrator is None:
            return FullMonitorModuleResult(
                module="source_refresh_orchestrator",
                status="SKIPPED",
                behavior=behavior,
                source="not_configured",
                warnings=["SOURCE_REFRESH_ORCHESTRATOR_NOT_CONFIGURED"],
            )
        if not self._governor.can_execute(RuntimeAction.COLLECT_DATA):
            return FullMonitorModuleResult(
                module="source_refresh_orchestrator",
                status="SKIPPED",
                behavior=behavior,
                source="StateGovernor",
                warnings=["SOURCE_REFRESH_BLOCKED_BY_MODE"],
            )
        try:
            if hasattr(self._source_refresh_orchestrator, "run_cycle"):
                result = self._source_refresh_orchestrator.run_cycle(candidate_limit=20)
            else:
                result = self._source_refresh_orchestrator()
                if inspect.isawaitable(result):
                    result = asyncio.run(result)
            data = result if isinstance(result, dict) else {}
            errors = [str(item) for item in data.get("errors", [])] if isinstance(data.get("errors"), list) else []
            if data.get("trading_mutation"):
                errors.append("SOURCE_REFRESH_TRADING_MUTATION_DETECTED")
            if data.get("status") in {"FAILED", "ERROR"}:
                errors.append(str(data.get("status")))
            warnings: list[str] = []
            if _safe_int(data.get("sources_failed")):
                warnings.append("SOURCE_REFRESH_PARTIAL_FAILURES")
            if _safe_int(data.get("derived_signals_created")) <= 0:
                warnings.append("DERIVED_SIGNALS_NOT_CREATED_THIS_CYCLE")
            return FullMonitorModuleResult(
                module="source_refresh_orchestrator",
                status="ERROR" if errors else "COMPLETED",
                behavior=behavior,
                source=self._source_refresh_orchestrator.__class__.__name__,
                counters={
                    "sources_checked": _safe_int(data.get("sources_checked")),
                    "sources_refreshed": _safe_int(data.get("sources_refreshed")),
                    "sources_failed": _safe_int(data.get("sources_failed")),
                    "sources_no_new_data": _safe_int(data.get("sources_no_new_data")),
                    "derived_signals_created": _safe_int(data.get("derived_signals_created")),
                },
                warnings=_unique(warnings),
                errors=errors,
            )
        except Exception as exc:
            return FullMonitorModuleResult(
                module="source_refresh_orchestrator",
                status="ERROR",
                behavior=behavior,
                source=self._source_refresh_orchestrator.__class__.__name__,
                errors=[f"{type(exc).__name__}: {exc}"],
            )

    def _run_read_only_module(self, module: str, behavior: str, getter: Any) -> FullMonitorModuleResult:
        try:
            envelope = getter(self._query_service)
            data = envelope.get("data") if isinstance(envelope, dict) else {}
            return FullMonitorModuleResult(
                module=module,
                status="COMPLETED",
                behavior=behavior,
                source=str(envelope.get("source")) if envelope.get("source") else None,
                counters=_extract_counters(data if isinstance(data, dict) else {}),
                warnings=[str(item) for item in envelope.get("warnings", [])] if isinstance(envelope, dict) else [],
                errors=[str(item) for item in envelope.get("errors", [])] if isinstance(envelope, dict) else [],
            )
        except Exception as exc:
            return FullMonitorModuleResult(module=module, status="ERROR", behavior=behavior, errors=[str(exc)])

    def _execute_paper_cycle(self, record: RuntimeSupervisorRecord) -> dict[str, Any]:
        try:
            control = self._paper_simulation.status_record(include_paper_truth=False)
        except TypeError:
            control = self._paper_simulation.status_record()
        except Exception as exc:
            return {
                "enabled": False,
                "status": "ERROR",
                "execution_enabled": False,
                "live_execution_enabled": False,
                "warnings": [],
                "errors": [f"Paper simulation status failed: {type(exc).__name__}: {exc}"],
            }

        if not bool(getattr(control, "enabled", False)) or getattr(control, "status", "DISABLED") != "ENABLED":
            return {
                "enabled": False,
                "status": getattr(control, "status", "DISABLED"),
                "execution_enabled": False,
                "live_execution_enabled": False,
                "warnings": list(getattr(control, "warnings", []) or []),
                "errors": list(getattr(control, "errors", []) or []),
                "reason": "paper_simulation_disabled",
            }

        cycle_id = f"{record.session_id}:{record.cycles_completed + 1}"
        correlation_id = f"paper_simulation_{uuid4().hex}"
        try:
            intent_run = self._paper_intents.build_intents(limit=20, write_intents=True, write_no_trade=True)
            execution_run = self._paper_execution.run_execution(limit=20, cycle_id=cycle_id, correlation_id=correlation_id)
            exit_run = self._paper_exits.run_exit_loop(limit=20, correlation_id=correlation_id)
            pnl_summary = self._paper_exits.get_pnl_dashboard_summary(limit=20)
        except Exception as exc:
            return {
                "enabled": True,
                "status": "ERROR",
                "execution_enabled": False,
                "live_execution_enabled": False,
                "warnings": [],
                "errors": [f"Paper simulation cycle failed: {type(exc).__name__}: {exc}"],
            }

        intents_created = _safe_int(intent_run.get("paper_intents_created")) + _safe_int(intent_run.get("paper_intents_updated"))
        no_trade_created = _safe_int(intent_run.get("no_trade_records_created")) + _safe_int(intent_run.get("no_trade_records_updated"))
        intent_blocked = _safe_int(intent_run.get("blocked_candidates")) + no_trade_created
        orders_created = _safe_int(execution_run.get("orders_created"))
        fills_created = _safe_int(execution_run.get("fills_created"))
        positions_created = _safe_int(execution_run.get("positions_created"))
        marked_positions = _safe_int(exit_run.get("marked_positions_count"))
        closed_positions = _safe_int(exit_run.get("closed_positions_count"))
        block_reasons = execution_run.get("block_reasons") if isinstance(execution_run, dict) else {}
        blockers = [f"{key}: {value}" for key, value in dict(block_reasons or {}).items()]
        if execution_run.get("status") and execution_run.get("status") not in {"OK"}:
            blockers.append(str(execution_run.get("status")))
        if intent_run.get("error_summary"):
            blockers.append(str(intent_run.get("error_summary")))
        if exit_run.get("error_summary"):
            blockers.append(str(exit_run.get("error_summary")))

        if orders_created:
            self._publish_event(EventType.EXECUTION_ORDER_SUBMITTED_PAPER.value, record, {"cycle_id": cycle_id, "orders_created": orders_created, "correlation_id": correlation_id})
        if fills_created:
            self._publish_event(EventType.EXECUTION_FILL_CREATED.value, record, {"cycle_id": cycle_id, "fills_created": fills_created, "correlation_id": correlation_id})
        if positions_created:
            self._publish_event(EventType.POSITION_OPENED.value, record, {"cycle_id": cycle_id, "positions_created": positions_created, "correlation_id": correlation_id})
        if no_trade_created or intent_blocked or blockers:
            self._publish_event(EventType.NO_TRADE_LOGGED.value, record, {"cycle_id": cycle_id, "no_trade_records": no_trade_created, "blocked_candidates": intent_blocked, "blockers": blockers[:8], "correlation_id": correlation_id})

        return {
            "enabled": True,
            "status": "ENABLED",
            "execution_enabled": False,
            "paper_execution_enabled": True,
            "live_execution_enabled": False,
            "paper_intents_created": intents_created,
            "paper_intents_blocked": intent_blocked,
            "paper_orders_created": orders_created,
            "paper_fills_created": fills_created,
            "paper_positions_opened": positions_created,
            "paper_positions_marked": marked_positions,
            "paper_positions_closed": closed_positions,
            "paper_pnl": pnl_summary if isinstance(pnl_summary, dict) else {},
            "paper_blockers": blockers[:12],
            "intent_run": intent_run,
            "execution_run": execution_run,
            "exit_run": exit_run,
            "warnings": [],
            "errors": [],
        }

    def _apply_cycle(self, record: RuntimeSupervisorRecord, module_results: list[FullMonitorModuleResult], paper_flow: dict[str, Any]) -> None:
        errors: list[str] = []
        warnings = list(record.warnings)
        for result in module_results:
            errors.extend(result.errors)
            warnings.extend(result.warnings)
        record.markets_checked += _counter(module_results, "market_scan", ("markets", "market_count", "total_markets", "total_scored", "source_counts"))
        record.events_seen += _counter(module_results, "events", ("events", "count"))
        record.opportunities_found += _counter(module_results, "opportunity", ("candidates", "count", "opportunities"))
        record.opportunities_found += _counter(module_results, "candidate_producer", ("candidates_created", "candidates_updated"))
        record.no_trades_logged += _counter(module_results, "no_trade", ("records", "items", "count", "no_trade_count"))
        ai_result = next((item for item in module_results if item.module == "ai"), None)
        if ai_result is not None:
            record.ai_calls += 1
            if ai_result.status == "ERROR" or ai_result.errors:
                record.ai_failures += 1
        record.paper_simulation_enabled = bool(paper_flow.get("enabled"))
        record.paper_simulation_status = str(paper_flow.get("status") or "DISABLED")
        record.paper_execution_enabled = bool(paper_flow.get("paper_execution_enabled")) and record.paper_simulation_enabled
        record.paper_intents_created += _safe_int(paper_flow.get("paper_intents_created"))
        record.paper_intents_blocked += _safe_int(paper_flow.get("paper_intents_blocked"))
        record.paper_orders_created += _safe_int(paper_flow.get("paper_orders_created"))
        record.paper_fills_created += _safe_int(paper_flow.get("paper_fills_created"))
        record.paper_positions_opened += _safe_int(paper_flow.get("paper_positions_opened"))
        record.paper_positions_marked += _safe_int(paper_flow.get("paper_positions_marked"))
        record.paper_orders = record.paper_orders_created if record.paper_simulation_enabled else 0
        record.paper_fills = record.paper_fills_created if record.paper_simulation_enabled else 0
        record.positions_updated = (record.paper_positions_opened + record.paper_positions_marked) if record.paper_simulation_enabled else 0
        record.paper_pnl = paper_flow.get("paper_pnl") if isinstance(paper_flow.get("paper_pnl"), dict) else record.paper_pnl
        record.paper_blockers = list(paper_flow.get("paper_blockers") or [])
        record.latest_paper_flow = {key: value for key, value in paper_flow.items() if key not in {"paper_pnl"}}
        source_refresh = next((item for item in module_results if item.module == "source_refresh_orchestrator"), None)
        if source_refresh is not None:
            record.source_refresh_orchestrator_state = "ACTIVE" if source_refresh.status == "COMPLETED" else source_refresh.status
            record.source_refresh_cycles_completed += 1 if source_refresh.status == "COMPLETED" else 0
            record.sources_refreshed_this_cycle = _safe_int(source_refresh.counters.get("sources_refreshed"))
            record.sources_failed_this_cycle = _safe_int(source_refresh.counters.get("sources_failed"))
            record.sources_no_new_data_this_cycle = _safe_int(source_refresh.counters.get("sources_no_new_data"))
            record.derived_signals_created_this_cycle = _safe_int(source_refresh.counters.get("derived_signals_created"))
            record.latest_source_refresh_at = utc_now_iso()
        record.execution_enabled = False
        errors.extend([str(item) for item in paper_flow.get("errors", [])])
        warnings.extend([str(item) for item in paper_flow.get("warnings", [])])
        record.errors = _unique([*record.errors, *errors])
        record.warnings = _unique(warnings)

    def _finish(self, record: RuntimeSupervisorRecord, status: RuntimeSupervisorStatus) -> RuntimeSupervisorRecord:
        now = utc_now_iso()
        record.supervisor_status = status
        record.current_cycle_status = status
        record.updated_at = now
        record.stopped_at = now
        record.next_cycle_at = None
        record.paper_simulation_enabled = False
        record.paper_simulation_status = "DISABLED"
        record.paper_execution_enabled = False
        self._write_report(record)
        self._store.set(record)
        return record

    def _start_lock_reason(self) -> str | None:
        try:
            state = self._governor.get_current_state()
        except RuntimeStateUnavailable as exc:
            return f"State Governor unavailable: {exc}"
        except Exception as exc:
            return f"State Governor check failed: {exc}"
        if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            return "KILL state is active; runtime supervisor start is blocked."
        if state.current_mode not in {RuntimeMode.DATA_ONLY, RuntimeMode.PAPER}:
            return "Runtime supervisor requires DATA_ONLY or PAPER runtime mode."
        if not self._governor.can_execute(RuntimeAction.COLLECT_DATA):
            return "State Governor does not allow DATA_ONLY data collection."
        if self._governor.can_execute(RuntimeAction.SEND_LIVE_ORDER):
            return "Current State Governor permissions allow live orders; runtime supervisor is locked."
        try:
            if bool(get_stage4_settings().live_trading_enabled):
                return "LIVE_TRADING_ENABLED is true; runtime supervisor is locked."
        except Exception as exc:
            return f"Live safety settings could not be loaded: {exc}"
        return None

    def _stop_reason(self) -> str | None:
        return self._start_lock_reason()

    def _safe_state(self) -> Any:
        try:
            return self._governor.get_current_state()
        except Exception:
            return None

    def _current_mode_value(self) -> str:
        state = self._safe_state()
        return str(getattr(getattr(state, "current_mode", None), "value", getattr(state, "current_mode", "UNKNOWN")))

    def _locked(self, payload: RuntimeSupervisorStartRequest, warning: str, *, interval_seconds: int) -> RuntimeSupervisorRecord:
        return RuntimeSupervisorRecord(
            supervisor_status="LOCKED",
            interval_seconds=interval_seconds,
            updated_at=utc_now_iso(),
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            warnings=[warning],
        )

    def _rejected(self, payload: RuntimeSupervisorStartRequest, errors: list[str]) -> RuntimeSupervisorRecord:
        return RuntimeSupervisorRecord(
            supervisor_status="REJECTED",
            updated_at=utc_now_iso(),
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            errors=errors,
        )

    def _publish_event(self, event_type: str, record: RuntimeSupervisorRecord, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(
                event_type,
                {"source": "runtime_supervisor", **payload},
                source_service="runtime_supervisor",
                aggregate_type="control_center_runtime_supervisor",
                aggregate_id=record.session_id,
                metadata={
                    "non_trading_event": True,
                    "execution_enabled": False,
                    "live_execution_enabled": False,
                    "paper_execution_enabled": bool(record.paper_execution_enabled),
                },
            )
        except Exception as exc:
            record.warnings = _unique([*record.warnings, f"Supervisor event logging failed: {type(exc).__name__}: {exc}"])

    def _write_report(self, record: RuntimeSupervisorRecord) -> None:
        if not record.session_id:
            return
        self._report_dir.mkdir(parents=True, exist_ok=True)
        md_path = self._report_dir / f"{record.session_id}.md"
        json_path = self._report_dir / f"{record.session_id}.json"
        record.report_path = str(md_path).replace("\\", "/")
        record.report_json_path = str(json_path).replace("\\", "/")
        json_path.write_text(_json_dumps(record.model_dump(mode="json")), encoding="utf-8")
        md_path.write_text(
            "\n".join(
                [
                    "# POLYBOT Runtime Supervisor Session Report",
                    "",
                    f"- session_id: `{record.session_id}`",
                    f"- status: `{record.supervisor_status}`",
                    f"- started_at: `{record.started_at}`",
                    f"- stopped_at: `{record.stopped_at}`",
                    f"- interval_seconds: `{record.interval_seconds}`",
                    f"- cycles_completed: `{record.cycles_completed}`",
                    f"- cycles_failed: `{record.cycles_failed}`",
                    f"- markets_checked: `{record.markets_checked}`",
                    f"- events_seen: `{record.events_seen}`",
                    f"- opportunities_found: `{record.opportunities_found}`",
                    f"- no_trades_logged: `{record.no_trades_logged}`",
                    f"- ai_calls: `{record.ai_calls}`",
                    f"- ai_failures: `{record.ai_failures}`",
                    f"- orders/fills/positions_created: `{record.paper_orders}/{record.paper_fills}/{record.positions_updated}`",
                    f"- paper_simulation_status: `{record.paper_simulation_status}`",
                    f"- paper_intents_created: `{record.paper_intents_created}`",
                    f"- paper_intents_blocked: `{record.paper_intents_blocked}`",
                    f"- paper_orders_created: `{record.paper_orders_created}`",
                    f"- paper_fills_created: `{record.paper_fills_created}`",
                    f"- paper_positions_opened: `{record.paper_positions_opened}`",
                    f"- paper_positions_marked: `{record.paper_positions_marked}`",
                    "",
                    "## Safety Summary",
                    "",
                    "- Safety mode: DATA_ONLY monitoring with optional explicit paper simulation.",
                    "- Execution enabled: false.",
                    f"- Paper simulation enabled at stop: {str(record.paper_simulation_enabled).lower()}.",
                    f"- Paper execution enabled at stop: {str(record.paper_execution_enabled).lower()}.",
                    "- Live execution enabled: false.",
                    "- No live trading orders were sent by this supervisor session.",
                    "- Any paper orders, fills, positions, and PnL above come only from canonical paper_* tables.",
                    "",
                    "## Paper Blockers",
                    "",
                    *([f"- {blocker}" for blocker in record.paper_blockers] or ["- None"]),
                    "",
                    "## Last Cycle Summary",
                    "",
                    "```json",
                    json.dumps(record.last_cycle_summary, indent=2, sort_keys=True),
                    "```",
                    "",
                    "## Warnings",
                    "",
                    *([f"- {warning}" for warning in record.warnings] or ["- None"]),
                    "",
                    "## Errors",
                    "",
                    *([f"- {error}" for error in record.errors] or ["- None"]),
                ]
            ),
            encoding="utf-8",
        )


def _bounded_interval(value: int | None) -> int:
    if value is None:
        return 60
    return min(300, max(30, int(value)))


def _expected_paper_adapter_delta(key: str, *, paper_mode: bool) -> bool:
    return paper_mode and key in {"paper_intents", "paper_orders", "paper_fills", "paper_positions"}


def _validate_operator(actor: str, reason: str) -> list[str]:
    errors: list[str] = []
    if not actor.strip():
        errors.append("actor is required")
    if not reason.strip():
        errors.append("reason is required")
    return errors


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _module_counters(module_results: list[FullMonitorModuleResult], module: str) -> dict[str, Any]:
    result = next((item for item in module_results if item.module == module), None)
    if result is None:
        return {}
    return dict(result.counters or {})


def _cycle_summary(module_results: list[FullMonitorModuleResult], paper_flow: dict[str, Any] | None = None) -> dict[str, Any]:
    paper_flow = paper_flow or {}
    return {
        "modules_completed": sum(1 for item in module_results if item.status == "COMPLETED"),
        "modules_skipped": sum(1 for item in module_results if item.status == "SKIPPED"),
        "modules_error": sum(1 for item in module_results if item.status == "ERROR"),
        "modules": [item.model_dump(mode="json") for item in module_results],
        "paper_simulation": {
            "enabled": bool(paper_flow.get("enabled")),
            "status": paper_flow.get("status") or "DISABLED",
            "paper_intents_created": _safe_int(paper_flow.get("paper_intents_created")),
            "paper_intents_blocked": _safe_int(paper_flow.get("paper_intents_blocked")),
            "paper_orders_created": _safe_int(paper_flow.get("paper_orders_created")),
            "paper_fills_created": _safe_int(paper_flow.get("paper_fills_created")),
            "paper_positions_opened": _safe_int(paper_flow.get("paper_positions_opened")),
            "paper_positions_marked": _safe_int(paper_flow.get("paper_positions_marked")),
            "paper_blockers": list(paper_flow.get("paper_blockers") or []),
        },
    }
