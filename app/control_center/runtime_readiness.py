from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.control_center.full_monitor_run_service import (
    DEFAULT_FULL_MONITOR_RUN_STORE,
    FullMonitorRunStore,
)
from app.control_center.runtime_supervisor import (
    DEFAULT_RUNTIME_SUPERVISOR_STORE,
    RuntimeSupervisorStore,
)
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    truth_envelope,
)
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.service_health_repository import ServiceHealthRepository
from app.runtime.modes import RuntimeAction, RuntimeMode
from app.runtime.state_governor import StateGovernor
from app.runtime.system_power import SystemPower


SCHEDULER_STALE_AFTER_SECONDS = 300
SUPERVISOR_STALE_AFTER_SECONDS = 300
FULL_MONITOR_STALE_AFTER_SECONDS = 300
CYCLE_STALE_AFTER_SECONDS = 600

SOURCE_MAP = {
    "system_power": "system_state.system_power",
    "state_governor": "StateGovernor.can_execute(COLLECT_DATA)",
    "scheduler": "service_health.scheduler",
    "runtime_supervisor": "PROCESS_LOCAL runtime_supervisor store",
    "runtime_cycles": "runtime_cycles_v2",
    "full_monitor_run": "PROCESS_LOCAL full_monitor_run store",
}


class RuntimeReadinessService:
    """Builds one read-only truth object for current runtime readiness."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        governor: StateGovernor | None = None,
        runtime_supervisor_store: RuntimeSupervisorStore | None = None,
        full_monitor_run_store: FullMonitorRunStore | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._governor = governor or StateGovernor(connection_factory=self._factory)
        self._states = RuntimeStateRepository()
        self._cycles = RuntimeCycleRepository()
        self._services = ServiceHealthRepository()
        self._runtime_supervisor_store = runtime_supervisor_store or DEFAULT_RUNTIME_SUPERVISOR_STORE
        self._full_monitor_run_store = full_monitor_run_store or DEFAULT_FULL_MONITOR_RUN_STORE

    def get_readiness(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        warnings: list[str] = []
        errors: list[str] = []
        blockers: list[str] = []
        state = None
        governor_allows_collect_data = False
        scheduler_row: dict[str, Any] | None = None
        active_cycle: dict[str, Any] | None = None
        last_successful_cycle: dict[str, Any] | None = None
        candidate_update: dict[str, Any] = {}

        if not self._factory.enabled:
            payload = self._payload(
                now=now,
                runtime_life_state="UNKNOWN",
                system_power_state="UNKNOWN",
                scheduler_state="UNKNOWN",
                scheduler_blocked_reason="DATABASE_NOT_CONFIGURED",
                supervisor_state=self._supervisor_state(now)["supervisor_state"],
                active_cycle_state="MISSING",
                last_successful_cycle_state="MISSING",
                full_monitor_run_state=self._full_monitor_state(now)["full_monitor_run_state"],
                governor_allows_collect_data=False,
                blockers=["DATABASE_NOT_CONFIGURED"],
                warnings=["Runtime readiness source is unavailable because the database is not configured."],
                errors=[],
            )
            return self._enveloped(payload, status=ControlCenterStatus.MISSING)

        try:
            with self._factory.connect() as conn:
                state = self._states.get_current_state(conn)
                with conn.transaction():
                    cutoff = now - timedelta(seconds=CYCLE_STALE_AFTER_SECONDS)
                    self._cycles.mark_stale_abandoned(conn, older_than=cutoff, reason="runtime_readiness_ttl_cleanup")
                    if state is not None and state.system_power.value == "OFF":
                        self._cycles.mark_open_cycles_safe_stopped(conn, reason="runtime_readiness_system_off_cleanup")
                scheduler_row = _to_dict(
                    conn.execute(
                        """
                        SELECT *
                        FROM service_health
                        WHERE service_name = 'scheduler'
                        ORDER BY updated_at DESC, id DESC
                        LIMIT 1
                        """
                    ).fetchone()
                )
                active_cycle = _to_dict(self._cycles.get_current_cycle(conn))
                last_successful_cycle = _to_dict(
                    conn.execute(
                        """
                        SELECT *
                        FROM runtime_cycles_v2
                        WHERE status = 'COMPLETED'
                        ORDER BY finished_at DESC NULLS LAST, started_at DESC, id DESC
                        LIMIT 1
                        """
                    ).fetchone()
                )
                transition_at = state.system_power_transition_at if state and state.system_power.value == "ON" else None
                candidate_update = _candidate_update_truth(conn, transition_at)
        except Exception as exc:
            payload = self._payload(
                now=now,
                runtime_life_state="UNKNOWN",
                system_power_state="UNKNOWN",
                scheduler_state="UNKNOWN",
                scheduler_blocked_reason="DATABASE_QUERY_FAILED",
                supervisor_state=self._supervisor_state(now)["supervisor_state"],
                active_cycle_state="MISSING",
                last_successful_cycle_state="MISSING",
                full_monitor_run_state=self._full_monitor_state(now)["full_monitor_run_state"],
                governor_allows_collect_data=False,
                blockers=["DATABASE_QUERY_FAILED"],
                warnings=warnings,
                errors=[f"Runtime readiness query failed: {type(exc).__name__}: {exc}"],
            )
            return self._enveloped(payload, status=ControlCenterStatus.ERROR)

        if state is None:
            blockers.append("MISSING_RUNTIME_STATE")
            system_power_state = "UNKNOWN"
        elif state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            blockers.append("KILL_MODE_ACTIVE")
            system_power_state = "KILL"
        else:
            system_power_state = state.system_power.value
            if state.system_power == SystemPower.OFF:
                blockers.append("SYSTEM_POWER_OFF")

        if state is not None:
            try:
                governor_allows_collect_data = self._governor.can_execute(RuntimeAction.COLLECT_DATA)
            except Exception as exc:
                warnings.append(f"State Governor permission check failed: {type(exc).__name__}: {exc}")
        if state is not None and not governor_allows_collect_data:
            blockers.append("GOVERNOR_DENIED_COLLECT_DATA")

        scheduler = self._scheduler_state(scheduler_row, governor_allows_collect_data, system_power_state, now)
        if scheduler["scheduler_blocked_reason"]:
            blockers.append(str(scheduler["scheduler_blocked_reason"]))
        if scheduler["scheduler_state"] in {"STALE", "UNKNOWN", "STOPPED"}:
            warnings.append(f"Scheduler state is {scheduler['scheduler_state']}.")

        supervisor = self._supervisor_state(now)
        if supervisor["supervisor_state"] in {"REGISTERED_NOT_RUNNING", "STOPPED", "STALE", "UNKNOWN"}:
            warnings.append(f"Runtime supervisor state is {supervisor['supervisor_state']}.")

        active_cycle_state = self._active_cycle_state(active_cycle, now)
        last_cycle_state = self._last_successful_cycle_state(last_successful_cycle, now)
        if active_cycle_state["active_cycle_state"] in {"RUNNING_STALE", "ABANDONED"}:
            blockers.append("ACTIVE_CYCLE_STALE")
        if last_cycle_state["last_successful_cycle_state"] == "MISSING":
            warnings.append("No successful runtime cycle is recorded.")
        elif last_cycle_state["last_successful_cycle_state"] == "STALE":
            blockers.append("LAST_SUCCESSFUL_CYCLE_STALE")
        if system_power_state == "ON" and candidate_update.get("candidate_producer_state") != "RUNNING":
            warnings.append(str(candidate_update.get("candidate_update_warning") or "CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON"))

        full_monitor = self._full_monitor_state(now)
        warnings.append("FULL_MONITOR_RUN_DIAGNOSTIC_ONLY")

        blockers = _unique(blockers)
        warnings = _unique(warnings)
        runtime_life_state = self._runtime_life_state(
            system_power_state=system_power_state,
            governor_allows_collect_data=governor_allows_collect_data,
            scheduler_state=str(scheduler["scheduler_state"]),
            supervisor_state=str(supervisor["supervisor_state"]),
            active_cycle_state=str(active_cycle_state["active_cycle_state"]),
            last_successful_cycle_state=str(last_cycle_state["last_successful_cycle_state"]),
            blockers=blockers,
        )
        payload = self._payload(
            now=now,
            runtime_life_state=runtime_life_state,
            system_power_state=system_power_state,
            scheduler_state=str(scheduler["scheduler_state"]),
            scheduler_blocked_reason=scheduler["scheduler_blocked_reason"],
            supervisor_state=str(supervisor["supervisor_state"]),
            active_cycle_state=str(active_cycle_state["active_cycle_state"]),
            last_successful_cycle_state=str(last_cycle_state["last_successful_cycle_state"]),
            full_monitor_run_state=str(full_monitor["full_monitor_run_state"]),
            governor_allows_collect_data=governor_allows_collect_data,
            blockers=blockers,
            warnings=warnings,
            errors=errors,
            scheduler=scheduler,
            supervisor=supervisor,
            active_cycle=active_cycle_state,
            last_successful_cycle=last_cycle_state,
            full_monitor=full_monitor,
            candidate_update=candidate_update,
            state={
                "current_mode": state.current_mode.value if state else None,
                "system_power": state.system_power.value if state else None,
                "kill_switch_active": state.kill_switch_active if state else True,
                "cooldown_active": state.cooldown_active if state else False,
                "attack_mode_active": state.attack_mode_active if state else False,
            },
        )
        return self._enveloped(payload, status=self._status_for_life(runtime_life_state, blockers))

    def _payload(self, *, now: datetime, **values: Any) -> dict[str, Any]:
        return {
            "runtime_life_state": values["runtime_life_state"],
            "system_power_state": values["system_power_state"],
            "governor_allows_collect_data": values["governor_allows_collect_data"],
            "scheduler_state": values["scheduler_state"],
            "scheduler_blocked_reason": values["scheduler_blocked_reason"],
            "supervisor_state": values["supervisor_state"],
            "active_cycle_state": values["active_cycle_state"],
            "last_successful_cycle_state": values["last_successful_cycle_state"],
            "full_monitor_run_state": values["full_monitor_run_state"],
            "full_monitor_run_label": "DIAGNOSTIC_ONLY",
            "full_monitor_truth_scope": "PROCESS_LOCAL",
            "runtime_supervisor_truth_scope": "PROCESS_LOCAL",
            "source_map": SOURCE_MAP,
            "generated_at": now.isoformat(),
            "blockers": list(values.get("blockers") or []),
            "warnings": list(values.get("warnings") or []),
            "errors": list(values.get("errors") or []),
            "scheduler": values.get("scheduler") or {},
            "runtime_supervisor": values.get("supervisor") or {},
            "active_cycle": values.get("active_cycle") or {},
            "last_successful_cycle": values.get("last_successful_cycle") or {},
            "full_monitor_run": values.get("full_monitor") or {},
            "candidate_producer_state": (values.get("candidate_update") or {}).get("candidate_producer_state", "UNKNOWN"),
            "candidates_updated_since_system_on": (values.get("candidate_update") or {}).get("candidates_updated_since_system_on", 0),
            "candidate_update_warning": (values.get("candidate_update") or {}).get("candidate_update_warning"),
            "candidate_update": values.get("candidate_update") or {},
            "state": values.get("state") or {},
        }

    def _scheduler_state(
        self,
        row: dict[str, Any] | None,
        governor_allows_collect_data: bool,
        system_power_state: str,
        now: datetime,
    ) -> dict[str, Any]:
        if row is None:
            return {
                "scheduler_state": "UNKNOWN",
                "scheduler_blocked_reason": "SCHEDULER_HEALTH_MISSING",
                "scheduler_last_heartbeat": None,
                "scheduler_age_seconds": None,
                "raw_status": None,
                "source": SOURCE_MAP["scheduler"],
            }
        last_seen = row.get("last_heartbeat_at") or row.get("last_success_at") or row.get("updated_at")
        freshness, age = classify_freshness(last_seen, stale_after_seconds=SCHEDULER_STALE_AFTER_SECONDS, now=now)
        status = str(row.get("status") or "UNKNOWN")
        blocked_reason = _details_text(row, "blocked_reason") or _details_text(row, "reason")
        scheduler_state = "UNKNOWN"
        if status == "BLOCKED_BY_MODE":
            scheduler_state = "RUNNING_BLOCKED"
            blocked_reason = blocked_reason or "SCHEDULER_BLOCKED_BY_MODE"
        elif freshness == ControlCenterFreshnessState.STALE or status == "STALE":
            scheduler_state = "STALE"
        elif status in {"RUNNING", "HEALTHY"} and governor_allows_collect_data:
            scheduler_state = "RUNNING_ALLOWED"
        elif status in {"RUNNING", "HEALTHY"} and not governor_allows_collect_data:
            scheduler_state = "RUNNING_BLOCKED"
            blocked_reason = blocked_reason or (
                "SYSTEM_POWER_OFF" if system_power_state == "OFF" else "GOVERNOR_DENIED_COLLECT_DATA"
            )
        elif status == "STOPPED":
            scheduler_state = "STOPPED"
        elif status in {"ERROR", "DEGRADED"}:
            scheduler_state = "STALE"
            blocked_reason = blocked_reason or f"SCHEDULER_{status}"
        return {
            "scheduler_state": scheduler_state,
            "scheduler_blocked_reason": blocked_reason,
            "scheduler_last_heartbeat": _iso(last_seen),
            "scheduler_age_seconds": age,
            "freshness_state": freshness.value,
            "raw_status": status,
            "source": SOURCE_MAP["scheduler"],
        }

    def _supervisor_state(self, now: datetime) -> dict[str, Any]:
        record = self._runtime_supervisor_store.get()
        if record is None:
            return {
                "supervisor_state": "REGISTERED_NOT_RUNNING",
                "supervisor_status": "IDLE",
                "supervisor_last_heartbeat": None,
                "supervisor_age_seconds": None,
                "truth_scope": "PROCESS_LOCAL",
                "source": SOURCE_MAP["runtime_supervisor"],
            }
        last_seen = record.updated_at or record.last_cycle_at or record.started_at
        freshness, age = classify_freshness(last_seen, stale_after_seconds=SUPERVISOR_STALE_AFTER_SECONDS, now=now)
        raw_status = record.supervisor_status
        if freshness == ControlCenterFreshnessState.STALE and raw_status in {"STARTING", "RUNNING", "DEGRADED"}:
            supervisor_state = "STALE"
        elif raw_status in {"STARTING", "RUNNING", "DEGRADED"}:
            supervisor_state = "RUNNING"
        elif raw_status == "IDLE":
            supervisor_state = "REGISTERED_NOT_RUNNING"
        elif raw_status in {"STOPPING", "STOPPED", "KILLED", "LOCKED", "REJECTED"}:
            supervisor_state = "STOPPED"
        else:
            supervisor_state = "UNKNOWN"
        return {
            "supervisor_state": supervisor_state,
            "supervisor_status": raw_status,
            "supervisor_last_heartbeat": _iso(last_seen),
            "supervisor_age_seconds": age,
            "session_id": record.session_id,
            "current_cycle_status": record.current_cycle_status,
            "last_cycle_at": record.last_cycle_at,
            "next_cycle_at": record.next_cycle_at,
            "truth_scope": "PROCESS_LOCAL",
            "source": SOURCE_MAP["runtime_supervisor"],
        }

    def _active_cycle_state(self, row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
        if row is None:
            return {
                "active_cycle_state": "MISSING",
                "cycle_id": None,
                "cycle_status": None,
                "last_updated": None,
                "age_seconds": None,
                "truth_state": ControlCenterTruthState.UNKNOWN.value,
                "source": SOURCE_MAP["runtime_cycles"],
            }
        last_seen = row.get("started_at")
        freshness, age = classify_freshness(last_seen, stale_after_seconds=CYCLE_STALE_AFTER_SECONDS, now=now)
        status = str(row.get("status") or "UNKNOWN")
        if status == "RUNNING" and freshness == ControlCenterFreshnessState.FRESH:
            state = "RUNNING_FRESH"
        elif status == "RUNNING":
            state = "RUNNING_STALE"
        elif freshness == ControlCenterFreshnessState.STALE:
            state = "ABANDONED"
        else:
            state = "FRESH"
        return {
            "active_cycle_state": state,
            "cycle_id": row.get("cycle_id"),
            "cycle_status": status,
            "last_updated": _iso(last_seen),
            "age_seconds": age,
            "freshness_state": freshness.value,
            "truth_state": truth_from_freshness(freshness, has_history=True).value,
            "source": SOURCE_MAP["runtime_cycles"],
        }

    def _last_successful_cycle_state(self, row: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
        if row is None:
            return {
                "last_successful_cycle_state": "MISSING",
                "cycle_id": None,
                "cycle_status": None,
                "last_updated": None,
                "age_seconds": None,
                "truth_state": ControlCenterTruthState.UNKNOWN.value,
                "source": SOURCE_MAP["runtime_cycles"],
            }
        last_seen = row.get("finished_at") or row.get("started_at")
        freshness, age = classify_freshness(last_seen, stale_after_seconds=CYCLE_STALE_AFTER_SECONDS, now=now)
        return {
            "last_successful_cycle_state": freshness.value,
            "cycle_id": row.get("cycle_id"),
            "cycle_status": row.get("status"),
            "last_updated": _iso(last_seen),
            "age_seconds": age,
            "freshness_state": freshness.value,
            "truth_state": truth_from_freshness(freshness, has_history=True).value,
            "source": SOURCE_MAP["runtime_cycles"],
        }

    def _full_monitor_state(self, now: datetime) -> dict[str, Any]:
        current = self._full_monitor_run_store.get_current()
        latest = self._full_monitor_run_store.get_latest()
        run = current or latest
        if run is None:
            return {
                "full_monitor_run_state": "DIAGNOSTIC_IDLE",
                "status": "IDLE",
                "run_id": None,
                "last_updated": None,
                "age_seconds": None,
                "label": "DIAGNOSTIC_ONLY",
                "truth_scope": "PROCESS_LOCAL",
                "source": SOURCE_MAP["full_monitor_run"],
            }
        last_seen = run.updated_at or run.completed_at or run.ended_at or run.started_at
        freshness, age = classify_freshness(last_seen, stale_after_seconds=FULL_MONITOR_STALE_AFTER_SECONDS, now=now)
        if freshness == ControlCenterFreshnessState.STALE and run.status in {"STARTING", "RUNNING", "STOPPING"}:
            state = "DIAGNOSTIC_STALE"
        elif run.status in {"STARTING", "RUNNING", "STOPPING"}:
            state = "DIAGNOSTIC_RUNNING"
        elif run.status in {"STOPPED", "COMPLETED", "FAILED", "REJECTED", "ERROR", "LOCKED"}:
            state = "DIAGNOSTIC_STOPPED"
        else:
            state = "UNKNOWN"
        return {
            "full_monitor_run_state": state,
            "status": run.status,
            "run_id": run.run_id,
            "last_updated": _iso(last_seen),
            "age_seconds": age,
            "label": "DIAGNOSTIC_ONLY",
            "truth_scope": "PROCESS_LOCAL",
            "execution_enabled": run.execution_enabled,
            "source": SOURCE_MAP["full_monitor_run"],
        }

    def _runtime_life_state(
        self,
        *,
        system_power_state: str,
        governor_allows_collect_data: bool,
        scheduler_state: str,
        supervisor_state: str,
        active_cycle_state: str,
        last_successful_cycle_state: str,
        blockers: list[str],
    ) -> str:
        if "MISSING_RUNTIME_STATE" in blockers:
            return "UNKNOWN"
        if system_power_state == "KILL":
            return "BLOCKED"
        if system_power_state == "OFF":
            return "STOPPED"
        if not governor_allows_collect_data or scheduler_state == "RUNNING_BLOCKED":
            return "BLOCKED"
        if active_cycle_state in {"RUNNING_STALE", "ABANDONED"}:
            return "STALE"
        if last_successful_cycle_state == "STALE":
            return "STALE"
        if scheduler_state == "RUNNING_ALLOWED" and (
            supervisor_state == "RUNNING" or active_cycle_state == "RUNNING_FRESH" or last_successful_cycle_state == "FRESH"
        ):
            return "ALIVE"
        if scheduler_state in {"UNKNOWN", "STOPPED"} and last_successful_cycle_state == "MISSING":
            return "UNKNOWN"
        return "BLOCKED" if blockers else "STOPPED"

    def _status_for_life(self, runtime_life_state: str, blockers: list[str]) -> ControlCenterStatus:
        if runtime_life_state == "ALIVE":
            return ControlCenterStatus.REAL
        if runtime_life_state == "STALE":
            return ControlCenterStatus.STALE
        if runtime_life_state == "BLOCKED" or blockers:
            return ControlCenterStatus.LOCKED
        if runtime_life_state == "STOPPED":
            return ControlCenterStatus.PARTIAL
        return ControlCenterStatus.MISSING

    def _enveloped(self, payload: dict[str, Any], *, status: ControlCenterStatus) -> dict[str, Any]:
        life = str(payload["runtime_life_state"])
        last_cycle = payload.get("last_successful_cycle") if isinstance(payload.get("last_successful_cycle"), dict) else {}
        freshness = _freshness_for_life(life, last_cycle)
        runtime_state = {
            "ALIVE": ControlCenterRuntimeState.RUNNING,
            "BLOCKED": ControlCenterRuntimeState.BLOCKED,
            "STOPPED": ControlCenterRuntimeState.STOPPED,
            "STALE": ControlCenterRuntimeState.STALE,
        }.get(life, ControlCenterRuntimeState.UNKNOWN)
        readiness_state = {
            "ALIVE": ControlCenterReadinessState.READY,
            "BLOCKED": ControlCenterReadinessState.BLOCKED,
            "STOPPED": ControlCenterReadinessState.NOT_READY,
            "STALE": ControlCenterReadinessState.NOT_READY,
        }.get(life, ControlCenterReadinessState.UNKNOWN)
        truth_state = (
            ControlCenterTruthState.ACTIVE_FRESH
            if life == "ALIVE"
            else ControlCenterTruthState.LAST_KNOWN
            if life in {"STOPPED", "STALE", "BLOCKED"}
            else ControlCenterTruthState.UNKNOWN
        )
        envelope = truth_envelope(
            status=status,
            source="runtime_state + StateGovernor + service_health + runtime_cycles_v2 + process_local_status",
            truth_state=truth_state,
            data=payload,
            last_updated=last_cycle.get("last_updated") or payload["generated_at"],
            stale_after_seconds=CYCLE_STALE_AFTER_SECONDS,
            age_seconds=last_cycle.get("age_seconds"),
            freshness_state=freshness,
            runtime_state=runtime_state,
            readiness_state=readiness_state,
            warnings=list(payload.get("warnings") or []),
            errors=list(payload.get("errors") or []),
        ).to_dict()
        return {**envelope, **payload}


def _freshness_for_life(life: str, last_cycle: dict[str, Any]) -> ControlCenterFreshnessState:
    if life == "ALIVE":
        return ControlCenterFreshnessState.FRESH
    if life == "STALE":
        return ControlCenterFreshnessState.STALE
    raw = last_cycle.get("freshness_state")
    if raw in {"FRESH", "STALE", "MISSING"}:
        return ControlCenterFreshnessState(str(raw))
    return ControlCenterFreshnessState.MISSING


def _details_text(row: dict[str, Any], key: str) -> str | None:
    details = row.get("details_json")
    if isinstance(details, dict) and details.get(key):
        return str(details[key])
    return None


def _candidate_update_truth(conn: Any, system_on_at: Any) -> dict[str, Any]:
    if not _table_exists(conn, "paper_eligibility_candidates"):
        return {
            "candidate_producer_state": "MISSING",
            "candidate_freshness_state": "MISSING",
            "candidates_updated_since_system_on": 0,
            "last_candidate_updated_at": None,
            "candidate_update_warning": "CANDIDATE_LEDGER_MISSING",
        }
    last_candidate = conn.execute(
        "SELECT MAX(COALESCE(updated_at, created_at)) AS ts, COUNT(*) AS total FROM paper_eligibility_candidates"
    ).fetchone()
    updated_since = 0
    if system_on_at is not None:
        updated_since = int(
            conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM paper_eligibility_candidates
                WHERE COALESCE(updated_at, created_at) >= %s
                """,
                (system_on_at,),
            ).fetchone()["count"]
            or 0
        )
    last_ts = (last_candidate or {}).get("ts")
    freshness = "MISSING"
    if last_ts is not None:
        parsed = last_ts if isinstance(last_ts, datetime) else None
        if parsed is not None and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if parsed is not None:
            freshness = "FRESH" if (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds() <= CYCLE_STALE_AFTER_SECONDS else "STALE"
    state = "RUNNING" if updated_since > 0 and freshness == "FRESH" else "STALE" if freshness == "STALE" else "BLOCKED" if int((last_candidate or {}).get("total") or 0) > 0 else "MISSING"
    warning = None if state == "RUNNING" else "CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON" if system_on_at is not None else "SYSTEM_ON_TIMESTAMP_MISSING"
    return {
        "candidate_producer_state": state,
        "candidate_freshness_state": freshness,
        "candidates_updated_since_system_on": updated_since,
        "last_candidate_updated_at": _iso(last_ts),
        "candidate_update_warning": warning,
    }


def _to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
