from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from app.control_center.full_monitor_run import (
    FullMonitorModuleResult,
    FullMonitorRunRecord,
    FullMonitorRunRequest,
    FullMonitorStopRequest,
    utc_now_iso,
)
from app.control_center.query_service import ControlCenterQueryService
from app.control_center.truth_contract import truth_envelope
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.runtime_errors import RuntimeStateUnavailable
from app.runtime.state_governor import StateGovernor
from app.stage4 import get_stage4_settings
from app.utils.json_safety import json_dumps


SAFE_ENVELOPE_MODULES: tuple[tuple[str, str, Callable[[ControlCenterQueryService], dict[str, Any]]], ...] = (
    ("market_scan", "Read-only overview source and market coverage summary.", lambda query: query.overview()),
    ("events", "Read-only live-flow event summary.", lambda query: query.live_flow()),
    ("health", "Read-only organ/service heartbeat summary.", lambda query: query.organs()),
    ("opportunity", "Read-only closest-actionable candidate summary.", lambda query: query.closest_actionable()),
    ("risk", "Read-only risk evidence summary.", lambda query: query.risk_evidence()),
    ("capital", "Read-only overview-backed capital summary when present.", lambda query: query.overview()),
    ("positions", "Read-only canonical positions summary.", lambda query: query.positions()),
    ("exit", "Read-only lifecycle governance/exit-adjacent summary.", lambda query: query.lifecycle_governance()),
    ("pnl", "Read-only paper PnL ledger summary.", lambda query: query.pnl_ledger()),
    ("no_trade", "Read-only no-trade ledger summary.", lambda query: query.no_trade()),
    ("ai", "Read-only AI context summary.", lambda query: query.ai()),
    ("logs", "Read-only logs/errors summary.", lambda query: query.logs()),
    ("memory", "Read-only truth-state/memory-adjacent summary.", lambda query: query.truth_state()),
)

SKIPPED_MODULES: tuple[tuple[str, str], ...] = (
    ("orderbook", "No safe Control Center read-only orderbook monitor endpoint exists in Stage 16."),
    ("news", "No safe Control Center read-only news monitor endpoint exists in Stage 16."),
    ("whale", "No safe Control Center read-only whale monitor endpoint exists in Stage 16."),
    ("social", "No safe Control Center read-only social monitor endpoint exists in Stage 16."),
    ("paper_execution", "Paper execution can create paper orders/fills and is skipped by this monitor run."),
    ("live_execution", "Live execution is forbidden and is never called by this monitor run."),
)


class FullMonitorRunStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._current: FullMonitorRunRecord | None = None
        self._latest: FullMonitorRunRecord | None = None
        self._stop_events: dict[str, Event] = {}

    def get_current(self) -> FullMonitorRunRecord | None:
        with self._lock:
            return deepcopy(self._current)

    def get_latest(self) -> FullMonitorRunRecord | None:
        with self._lock:
            return deepcopy(self._latest)

    def set_current(self, run: FullMonitorRunRecord | None) -> None:
        with self._lock:
            self._current = deepcopy(run)
            if run is not None:
                self._latest = deepcopy(run)

    def set_latest(self, run: FullMonitorRunRecord) -> None:
        with self._lock:
            if run.status in {"STARTING", "RUNNING", "STOPPING"}:
                self._current = deepcopy(run)
            else:
                self._current = None
            self._latest = deepcopy(run)

    def update_run(self, run: FullMonitorRunRecord) -> None:
        self.set_latest(run)

    def register_stop_event(self, run_id: str, event: Event) -> None:
        with self._lock:
            self._stop_events[run_id] = event

    def stop_event(self, run_id: str) -> Event | None:
        with self._lock:
            return self._stop_events.get(run_id)

    def clear_stop_event(self, run_id: str) -> None:
        with self._lock:
            self._stop_events.pop(run_id, None)


DEFAULT_FULL_MONITOR_RUN_STORE = FullMonitorRunStore()


class FullMonitorRunService:
    def __init__(
        self,
        *,
        governor: StateGovernor | None = None,
        query_service: ControlCenterQueryService | None = None,
        store: FullMonitorRunStore | None = None,
        run_in_background: bool = True,
        report_dir: Path | str = "run_reports/control_center_monitor_runs",
        sleep_between_cycles: bool = True,
    ) -> None:
        self._governor = governor or StateGovernor()
        self._query_service = query_service or ControlCenterQueryService()
        self._store = store or DEFAULT_FULL_MONITOR_RUN_STORE
        self._run_in_background = run_in_background
        self._report_dir = Path(report_dir)
        self._sleep_between_cycles = sleep_between_cycles

    def start(self, payload: FullMonitorRunRequest) -> FullMonitorRunRecord:
        errors = self._validate_start(payload)
        if errors:
            return self._rejected(payload, errors)

        state_check = self._state_governor_check()
        if state_check:
            return self._locked(payload, state_check)

        live_check = self._live_disabled_check()
        if live_check:
            return self._locked(payload, live_check)

        active = self._store.get_current()
        if active and active.status in {"STARTING", "RUNNING", "STOPPING"}:
            return self._locked(payload, f"Full Monitor Run already running: {active.run_id}")

        duration_minutes = payload.duration_minutes or 1
        interval_seconds = payload.interval_seconds or 60
        now = utc_now_iso()
        run = FullMonitorRunRecord(
            run_id=f"full_monitor_run_{uuid4().hex}",
            status="STARTING",
            started_at=now,
            updated_at=now,
            requested_duration_minutes=duration_minutes,
            duration_minutes=duration_minutes,
            interval_seconds=interval_seconds,
            remaining_seconds=duration_minutes * 60,
            next_cycle_in_seconds=0,
            audit_id=f"control_center_full_monitor_run:{uuid4().hex}",
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            max_cycles=payload.max_cycles,
            warnings=[
                "Stage 25 monitoring run is continuous, bounded, and read-only/evaluation-only.",
                "Monitoring only. No paper execution enabled in this phase.",
            ],
        )
        self._store.set_current(run)
        stop_event = Event()
        self._store.register_stop_event(run.run_id, stop_event)
        if self._run_in_background:
            Thread(target=self._run_loop_safe, args=(run, stop_event), name=f"polybot-monitor-{run.run_id}", daemon=True).start()
            return self._store.get_latest() or run
        completed = self._run_loop(run, stop_event, wait_for_duration=False)
        self._store.set_latest(completed)
        return completed

    def stop(self, payload: FullMonitorStopRequest) -> FullMonitorRunRecord:
        errors = self._validate_operator(payload.actor, payload.reason)
        if errors:
            return self._stop_response(payload, status="REJECTED", errors=errors)

        active = self._store.get_current()
        if active is None:
            return self._stop_response(
                payload,
                status="STOPPED",
                warnings=["No active Full Monitor Run exists. Stop request recorded as safe no-op."],
            )

        now = utc_now_iso()
        active.status = "STOPPING"
        active.updated_at = now
        active.warnings = _unique([*active.warnings, f"Stop requested by {payload.actor.strip()}: {payload.reason.strip()}"])
        stop_event = self._store.stop_event(active.run_id)
        if stop_event:
            stop_event.set()
        else:
            active.status = "STOPPED"
            active.stopped_at = now
            active.ended_at = now
            active.elapsed_seconds = _elapsed_seconds(active.started_at, now)
        self._store.set_latest(active)
        return active

    def status(self) -> dict[str, Any]:
        current = self._store.get_current()
        latest = self._store.get_latest()
        run = current or latest
        if run is None:
            return truth_envelope(
                status="MISSING",
                source="control_center:full_monitor_run",
                truth_state="UNKNOWN",
            data={
                "run_type": "FULL_MONITOR_RUN",
                "current": None,
                "latest": None,
                "available": True,
                "safety_mode": "DATA_ONLY_MONITORING",
                "execution_enabled": False,
            },
                warnings=["No Full Monitor Run has been started in this process."],
            ).to_dict()

        return truth_envelope(
            status="REAL" if run.status in {"RUNNING", "COMPLETED", "STOPPED"} else "PARTIAL",
            source="control_center:full_monitor_run",
            truth_state="ACTIVE_FRESH" if run.status == "RUNNING" else "LAST_KNOWN",
            data={
                "run_type": "FULL_MONITOR_RUN",
                "current": current.to_action_result() if current else None,
                "latest": latest.to_action_result() if latest else None,
                "available": True,
                "safety_mode": "DATA_ONLY_MONITORING",
                "execution_enabled": False,
            },
            last_updated=run.updated_at or run.ended_at or run.stopped_at or run.started_at,
            stale_after_seconds=300,
            warnings=run.warnings,
            errors=run.errors,
        ).to_dict()

    def _run_loop_safe(self, run: FullMonitorRunRecord, stop_event: Event) -> None:
        try:
            self._run_loop(run, stop_event, wait_for_duration=True)
        finally:
            self._store.clear_stop_event(run.run_id)

    def _run_loop(self, run: FullMonitorRunRecord, stop_event: Event, *, wait_for_duration: bool) -> FullMonitorRunRecord:
        start_monotonic = monotonic()
        duration_seconds = max(60, int(run.requested_duration_minutes * 60))
        max_cycles = (
            max(1, (duration_seconds // max(1, run.interval_seconds)) + 1)
            if wait_for_duration
            else max(1, run.max_cycles)
        )
        run.status = "RUNNING"
        run.updated_at = utc_now_iso()
        self._store.update_run(run)

        while True:
            if stop_event.is_set():
                return self._finish_run(run, "STOPPED", start_monotonic, stopped=True)

            module_results = self._execute_cycle()
            run.module_results = module_results
            run.cycles_completed += 1
            self._apply_cycle_totals(run, module_results)
            self._refresh_timing(run, start_monotonic, duration_seconds)
            run.status = "RUNNING"
            run.updated_at = utc_now_iso()
            self._store.update_run(run)

            elapsed = monotonic() - start_monotonic
            if elapsed >= duration_seconds or run.cycles_completed >= max_cycles:
                return self._finish_run(run, "COMPLETED", start_monotonic)

            wait_seconds = min(run.interval_seconds, max(0.0, duration_seconds - elapsed))
            run.next_cycle_in_seconds = wait_seconds
            run.updated_at = utc_now_iso()
            self._store.update_run(run)
            if wait_for_duration and self._sleep_between_cycles:
                if stop_event.wait(wait_seconds):
                    return self._finish_run(run, "STOPPED", start_monotonic, stopped=True)
            else:
                return self._finish_run(run, "COMPLETED", start_monotonic)

    def _execute_cycle(self) -> list[FullMonitorModuleResult]:
        module_results: list[FullMonitorModuleResult] = []
        for module, behavior, getter in SAFE_ENVELOPE_MODULES:
            module_results.append(self._run_read_only_module(module, behavior, getter))
        for module, reason in SKIPPED_MODULES:
            module_results.append(
                FullMonitorModuleResult(
                    module=module,
                    status="SKIPPED",
                    behavior=reason,
                    warnings=[reason],
                )
            )
        return module_results

    def _apply_cycle_totals(self, run: FullMonitorRunRecord, module_results: list[FullMonitorModuleResult]) -> None:
        errors: list[str] = []
        warnings = list(run.warnings)
        for result in module_results:
            errors.extend(result.errors)
            warnings.extend(result.warnings)
        run.markets_checked += _counter(module_results, "market_scan", ("markets", "market_count", "total_markets", "total_scored", "source_counts"))
        run.events_created = 0
        run.events_seen += _counter(module_results, "events", ("events", "count"))
        run.opportunities_found += _counter(module_results, "opportunity", ("candidates", "count", "opportunities"))
        run.no_trades_logged += _counter(module_results, "no_trade", ("records", "items", "count", "no_trade_count"))
        run.modules_completed += sum(1 for result in module_results if result.status == "COMPLETED")
        run.modules_skipped += sum(1 for result in module_results if result.status == "SKIPPED")
        run.paper_orders = 0
        run.paper_fills = 0
        run.positions_updated = 0
        run.errors = _unique([*run.errors, *errors])
        run.warnings = _unique(warnings)

    def _refresh_timing(self, run: FullMonitorRunRecord, start_monotonic: float, duration_seconds: int) -> None:
        elapsed = max(0.0, monotonic() - start_monotonic)
        run.elapsed_seconds = elapsed
        run.remaining_seconds = max(0.0, duration_seconds - elapsed)

    def _finish_run(self, run: FullMonitorRunRecord, status: str, start_monotonic: float, *, stopped: bool = False) -> FullMonitorRunRecord:
        now = utc_now_iso()
        self._refresh_timing(run, start_monotonic, int(run.requested_duration_minutes * 60))
        run.status = status  # type: ignore[assignment]
        run.updated_at = now
        run.ended_at = now
        run.completed_at = now if status == "COMPLETED" else None
        run.stopped_at = now if stopped else run.stopped_at
        run.next_cycle_in_seconds = None
        if run.errors and run.cycles_completed == 0:
            run.status = "FAILED"
        self._write_report(run)
        self._store.set_latest(run)
        return run

    def _run_read_only_module(
        self,
        module: str,
        behavior: str,
        getter: Callable[[ControlCenterQueryService], dict[str, Any]],
    ) -> FullMonitorModuleResult:
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
            return FullMonitorModuleResult(
                module=module,
                status="ERROR",
                behavior=behavior,
                errors=[str(exc)],
            )

    def _validate_start(self, payload: FullMonitorRunRequest) -> list[str]:
        errors = self._validate_operator(payload.actor, payload.reason)
        if payload.duration_minutes is None:
            errors.append("duration_minutes is required")
        elif payload.duration_minutes < 1 or payload.duration_minutes > 60:
            errors.append("duration_minutes must be between 1 and 60")
        if payload.interval_seconds is None:
            errors.append("interval_seconds is required")
        elif payload.interval_seconds < 10 or payload.interval_seconds > 300:
            errors.append("interval_seconds must be between 10 and 300")
        return errors

    def _validate_operator(self, actor: str, reason: str) -> list[str]:
        errors: list[str] = []
        if not actor.strip():
            errors.append("actor is required")
        if not reason.strip():
            errors.append("reason is required")
        return errors

    def _state_governor_check(self) -> str | None:
        try:
            state = self._governor.get_current_state()
        except RuntimeStateUnavailable as exc:
            return f"State Governor unavailable: {exc}"
        except Exception as exc:
            return f"State Governor check failed: {exc}"
        if state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            return "KILL state is active; Full Monitor Run start is blocked."
        if state.current_mode != RuntimeMode.DATA_ONLY:
            return "Full Monitor Run requires DATA_ONLY monitoring mode."
        if not self._governor.can_execute(RuntimeAction.COLLECT_DATA):
            return "State Governor does not allow monitoring/data collection in the current mode."
        if self._governor.can_execute(RuntimeAction.SEND_LIVE_ORDER):
            return "Current State Governor permissions allow live orders; Full Monitor Run is locked."
        return None

    def _live_disabled_check(self) -> str | None:
        try:
            stage4 = get_stage4_settings()
        except Exception as exc:
            return f"Live safety settings could not be loaded: {exc}"
        if bool(stage4.live_trading_enabled):
            return "LIVE_TRADING_ENABLED is true; Full Monitor Run is locked."
        return None

    def _rejected(self, payload: FullMonitorRunRequest, errors: list[str]) -> FullMonitorRunRecord:
        return FullMonitorRunRecord(
            run_id=f"full_monitor_run_rejected_{uuid4().hex}",
            status="REJECTED",
            started_at=utc_now_iso(),
            requested_duration_minutes=payload.duration_minutes or 0,
            duration_minutes=payload.duration_minutes,
            interval_seconds=payload.interval_seconds or 0,
            audit_id=f"control_center_full_monitor_run_rejected:{uuid4().hex}",
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            max_cycles=payload.max_cycles,
            errors=errors,
        )

    def _locked(self, payload: FullMonitorRunRequest, warning: str) -> FullMonitorRunRecord:
        return FullMonitorRunRecord(
            run_id=f"full_monitor_run_locked_{uuid4().hex}",
            status="LOCKED",
            started_at=utc_now_iso(),
            requested_duration_minutes=payload.duration_minutes or 0,
            duration_minutes=payload.duration_minutes,
            interval_seconds=payload.interval_seconds or 0,
            audit_id=f"control_center_full_monitor_run_locked:{uuid4().hex}",
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            max_cycles=payload.max_cycles,
            warnings=[warning],
        )

    def _stop_response(
        self,
        payload: FullMonitorStopRequest,
        *,
        status: str,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> FullMonitorRunRecord:
        now = utc_now_iso()
        return FullMonitorRunRecord(
            run_id=f"full_monitor_stop_{uuid4().hex}",
            status=status,  # type: ignore[arg-type]
            started_at=now,
            stopped_at=now,
            ended_at=now,
            requested_duration_minutes=0,
            duration_minutes=0,
            interval_seconds=0,
            audit_id=f"control_center_full_monitor_stop:{uuid4().hex}",
            actor=payload.actor.strip(),
            reason=payload.reason.strip(),
            warnings=warnings or [],
            errors=errors or [],
        )

    def _write_report(self, run: FullMonitorRunRecord) -> None:
        self._report_dir.mkdir(parents=True, exist_ok=True)
        md_path = self._report_dir / f"{run.run_id}.md"
        json_path = self._report_dir / f"{run.run_id}.json"
        run.report_path = str(md_path).replace("\\", "/")
        run.report_json_path = str(json_path).replace("\\", "/")
        summary = run.model_dump(mode="json")
        json_path.write_text(_json_dumps(summary), encoding="utf-8")
        module_lines = "\n".join(
            f"- {item.module}: {item.status} ({item.behavior})"
            for item in run.module_results
        )
        md_path.write_text(
            "\n".join(
                [
                    f"# POLYBOT Full Monitor Run Report",
                    "",
                    f"- run_id: `{run.run_id}`",
                    f"- status: `{run.status}`",
                    f"- started_at: `{run.started_at}`",
                    f"- ended_at: `{run.ended_at}`",
                    f"- duration_minutes: `{run.requested_duration_minutes}`",
                    f"- interval_seconds: `{run.interval_seconds}`",
                    f"- cycles_completed: `{run.cycles_completed}`",
                    f"- markets_checked: `{run.markets_checked}`",
                    f"- events_seen: `{run.events_seen}`",
                    f"- opportunities_found: `{run.opportunities_found}`",
                    f"- no_trades_logged: `{run.no_trades_logged}`",
                    f"- paper_orders: `{run.paper_orders}`",
                    f"- paper_fills: `{run.paper_fills}`",
                    f"- positions_updated: `{run.positions_updated}`",
                    "",
                    "## Safety Summary",
                    "",
                    "- Safety mode: DATA_ONLY_MONITORING",
                    "- Execution enabled: false",
                    "- Monitoring only. No paper execution enabled in this phase.",
                    "- No live trading, orders, fills, or positions were created by this run.",
                    "",
                    "## Module Summary",
                    "",
                    module_lines or "- No module results recorded.",
                    "",
                    "## Warnings",
                    "",
                    *[f"- {warning}" for warning in run.warnings],
                    "",
                    "## Errors",
                    "",
                    *([f"- {error}" for error in run.errors] or ["- None"]),
                    "",
                    "## Recommended Next Checks",
                    "",
                    "- Review stale or partial source warnings in the Control Center.",
                    "- Keep PAPER/LIVE execution disabled unless a later reviewed phase explicitly enables it.",
                ]
            ),
            encoding="utf-8",
        )


def _extract_counters(data: dict[str, Any]) -> dict[str, int]:
    counters: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            counters[key] = value
        elif isinstance(value, list):
            counters[key] = len(value)
        elif isinstance(value, dict):
            nested_count = sum(1 for _ in value)
            if nested_count:
                counters[key] = nested_count
    return counters


def _counter(results: list[FullMonitorModuleResult], module: str, keys: tuple[str, ...]) -> int:
    for result in results:
        if result.module != module:
            continue
        for key in keys:
            value = result.counters.get(key)
            if isinstance(value, int):
                return value
    return 0


def _elapsed_seconds(started_at: str, ended_at: str) -> float:
    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(ended_at)
        return max(0.0, (end - start).total_seconds())
    except Exception:
        return 0.0


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _json_dumps(value: Any) -> str:
    return json_dumps(value, indent=2, sort_keys=True)
