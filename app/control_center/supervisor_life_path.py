from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.full_monitor_run_service import DEFAULT_FULL_MONITOR_RUN_STORE, FullMonitorRunStore
from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.runtime_supervisor import DEFAULT_RUNTIME_SUPERVISOR_STORE, RuntimeSupervisorStore
from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    truth_envelope,
)
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_state_repository import RuntimeStateRepository


SUPERVISOR_HEARTBEAT_STALE_SECONDS = 120

SOURCE_MAP = {
    "system_power": "system_state.system_power",
    "runtime_readiness": "/dashboard/api/v2/control/runtime-readiness",
    "runtime_supervisor": "PROCESS_LOCAL runtime_supervisor store",
    "runtime_cycles": "runtime_cycles_v2",
    "events": "event_log",
    "candidates": "paper_eligibility_candidates",
    "paper_readiness": "/dashboard/api/v2/control/paper-readiness",
    "full_monitor_run": "PROCESS_LOCAL full_monitor_run store",
}


class SupervisorLifePathService:
    """Read-only truth summary for SYSTEM ON -> supervisor -> cycles -> SYSTEM OFF."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        runtime_supervisor_store: RuntimeSupervisorStore | None = None,
        full_monitor_run_store: FullMonitorRunStore | None = None,
        runtime_readiness: RuntimeReadinessService | None = None,
        paper_readiness: PaperReadinessService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._supervisor_store = runtime_supervisor_store or DEFAULT_RUNTIME_SUPERVISOR_STORE
        self._full_monitor_store = full_monitor_run_store or DEFAULT_FULL_MONITOR_RUN_STORE
        self._runtime_readiness = runtime_readiness or RuntimeReadinessService(
            connection_factory=self._factory,
            runtime_supervisor_store=self._supervisor_store,
            full_monitor_run_store=self._full_monitor_store,
        )
        self._paper_readiness = paper_readiness or PaperReadinessService(connection_factory=self._factory)
        self._states = RuntimeStateRepository()

    def get_life_path(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        warnings: list[str] = []
        errors: list[str] = []
        blockers: list[str] = []
        db_truth = self._db_truth(now, errors)
        supervisor = self._supervisor_truth(now)
        runtime_readiness = self._safe_runtime_readiness(errors)
        paper_readiness = self._safe_paper_readiness(errors)
        full_monitor = self._full_monitor_truth(now)

        system_power = db_truth.get("system_power_state") or runtime_readiness.get("system_power_state") or "UNKNOWN"
        runtime_life = runtime_readiness.get("runtime_life_state") or "UNKNOWN"
        supervisor_state = supervisor["supervisor_state"]
        cycle_state = self._cycle_state(supervisor, db_truth, system_power)

        if system_power == "OFF":
            blockers.append("SYSTEM_POWER_OFF")
        if supervisor_state in {"STOPPED", "STALE", "UNKNOWN"}:
            blockers.append(f"SUPERVISOR_{supervisor_state}")
        if supervisor_state == "REGISTERED_NOT_RUNNING":
            blockers.append("SUPERVISOR_REGISTERED_NOT_RUNNING")
        if cycle_state in {"CYCLE_STALE", "UNKNOWN"} and system_power == "ON":
            blockers.append("SUPERVISOR_CYCLE_NOT_FRESH")
        if paper_readiness.get("paper_simulation_state") == "OFF":
            warnings.append("PAPER_SIMULATION_OFF")
        if full_monitor["full_monitor_run_state"] == "DIAGNOSTIC_RUNNING":
            warnings.append("Full Monitor Run is diagnostic-only and does not contribute to supervisor life.")

        events_updated = _positive(db_truth.get("events_since_system_on"))
        candidates_updated = _positive(db_truth.get("candidates_updated_since_system_on"))
        runtime_readiness_updated = runtime_life in {"ALIVE", "PARTIAL", "BLOCKED", "STOPPED"}
        paper_readiness_updated = bool(paper_readiness.get("last_updated") or paper_readiness.get("generated_at"))
        supervisor_cycles_completed = int(supervisor.get("cycles_completed") or 0)
        scheduler_cycles_completed = int(db_truth.get("cycles_completed_since_system_on") or 0)
        if system_power == "ON":
            if not events_updated:
                warnings.append("EVENTS_NOT_UPDATED_SINCE_SYSTEM_ON")
            if not candidates_updated:
                warnings.append("CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON")

        supervisor_life_state = self._life_state(
            system_power=system_power,
            supervisor_state=supervisor_state,
            cycle_state=cycle_state,
            supervisor_freshness=supervisor["freshness_state"],
            blockers=blockers,
        )
        readiness_state = _readiness_for_life(supervisor_life_state)
        freshness_state = self._freshness(supervisor, db_truth)
        truth_state = truth_from_freshness(freshness_state, has_history=bool(supervisor.get("supervisor_last_heartbeat") or db_truth.get("last_cycle_completed_at"))).value
        status = _status_for_life(supervisor_life_state)

        payload = {
            "supervisor_life_state": supervisor_life_state,
            "system_power_state": system_power,
            "runtime_life_state": runtime_life,
            "supervisor_state": supervisor_state,
            "supervisor_last_heartbeat": supervisor.get("supervisor_last_heartbeat"),
            "supervisor_age_seconds": supervisor.get("supervisor_age_seconds"),
            "cycle_state": cycle_state,
            "cycles_completed_since_system_on": supervisor_cycles_completed if system_power == "ON" else 0,
            "scheduler_cycles_completed_since_system_on": scheduler_cycles_completed if system_power == "ON" else 0,
            "last_cycle_id": db_truth.get("last_cycle_id"),
            "last_cycle_started_at": db_truth.get("last_cycle_started_at"),
            "last_cycle_completed_at": db_truth.get("last_cycle_completed_at"),
            "last_cycle_age_seconds": db_truth.get("last_cycle_age_seconds"),
            "events_updated": events_updated,
            "candidates_updated": candidates_updated,
            "runtime_readiness_updated": runtime_readiness_updated,
            "paper_readiness_updated": paper_readiness_updated,
            "full_monitor_run_label": "DIAGNOSTIC_ONLY",
            "full_monitor_run_state": full_monitor["full_monitor_run_state"],
            "blockers": _unique(blockers),
            "warnings": _unique(warnings + list(db_truth.get("warnings") or [])),
            "errors": _unique(errors),
            "source": SOURCE_MAP,
            "runtime_readiness": _compact_runtime(runtime_readiness),
            "paper_readiness": _compact_paper(paper_readiness),
            "runtime_supervisor": supervisor.get("raw") or {},
            "full_monitor_run": full_monitor.get("raw") or {},
            "counts": {
                "events_since_system_on": db_truth.get("events_since_system_on", 0),
                "candidates_updated_since_system_on": db_truth.get("candidates_updated_since_system_on", 0),
                "supervisor_cycles_completed_since_system_on": supervisor_cycles_completed if system_power == "ON" else 0,
                "scheduler_cycles_completed_since_system_on": scheduler_cycles_completed if system_power == "ON" else 0,
                "paper_intents": db_truth.get("paper_intents", 0),
                "paper_orders": db_truth.get("paper_orders", 0),
                "paper_fills": db_truth.get("paper_fills", 0),
                "paper_positions": db_truth.get("paper_positions", 0),
                "paper_position_closes": db_truth.get("paper_position_closes", 0),
                "live_orders": db_truth.get("live_orders", 0),
                "orders_v2": db_truth.get("orders_v2", 0),
                "fills_v2": db_truth.get("fills_v2", 0),
                "positions": db_truth.get("positions", 0),
            },
            "system_power_transition_at": db_truth.get("system_power_transition_at"),
            "last_updated": now.isoformat(),
        }
        envelope = truth_envelope(
            status=status,
            source="supervisor life path: system_state + process-local supervisor + runtime_cycles_v2 + event/candidate/readiness sources",
            truth_state=truth_state,
            data=payload,
            last_updated=payload["supervisor_last_heartbeat"] or payload["last_cycle_completed_at"] or payload["last_updated"],
            stale_after_seconds=SUPERVISOR_HEARTBEAT_STALE_SECONDS,
            age_seconds=payload["supervisor_age_seconds"] if payload["supervisor_age_seconds"] is not None else payload["last_cycle_age_seconds"],
            freshness_state=freshness_state,
            runtime_state=_runtime_state_for_life(supervisor_life_state),
            readiness_state=readiness_state,
            warnings=payload["warnings"],
            errors=payload["errors"],
        ).to_dict()
        return {**envelope, **payload}

    def _safe_runtime_readiness(self, errors: list[str]) -> dict[str, Any]:
        try:
            return self._runtime_readiness.get_readiness()
        except Exception as exc:
            errors.append(f"Runtime readiness unavailable: {type(exc).__name__}: {exc}")
            return {}

    def _safe_paper_readiness(self, errors: list[str]) -> dict[str, Any]:
        try:
            return self._paper_readiness.get_readiness()
        except Exception as exc:
            errors.append(f"Paper readiness unavailable: {type(exc).__name__}: {exc}")
            return {}

    def _supervisor_truth(self, now: datetime) -> dict[str, Any]:
        record = self._supervisor_store.get()
        if record is None:
            return {
                "supervisor_state": "REGISTERED_NOT_RUNNING",
                "supervisor_status": "IDLE",
                "supervisor_last_heartbeat": None,
                "supervisor_age_seconds": None,
                "freshness_state": ControlCenterFreshnessState.MISSING.value,
                "raw": {},
            }
        last_seen = record.updated_at or record.last_cycle_at or record.started_at
        freshness, age = classify_freshness(last_seen, stale_after_seconds=SUPERVISOR_HEARTBEAT_STALE_SECONDS, now=now)
        status = str(record.supervisor_status or "UNKNOWN")
        if freshness == ControlCenterFreshnessState.STALE and status in {"STARTING", "RUNNING", "DEGRADED"}:
            state = "STALE"
        elif status in {"STARTING", "RUNNING"}:
            state = "ALIVE"
        elif status == "DEGRADED":
            state = "PARTIAL"
        elif status in {"STOPPING", "STOPPED", "KILLED", "LOCKED", "REJECTED"}:
            state = "STOPPED"
        elif status == "IDLE":
            state = "REGISTERED_NOT_RUNNING"
        else:
            state = "UNKNOWN"
        return {
            "supervisor_state": state,
            "supervisor_status": status,
            "supervisor_last_heartbeat": _iso(last_seen),
            "supervisor_age_seconds": age,
            "cycles_completed": int(record.cycles_completed or 0),
            "current_cycle_status": record.current_cycle_status,
            "last_cycle_at": record.last_cycle_at,
            "freshness_state": freshness.value,
            "raw": record.to_action_result(),
        }

    def _full_monitor_truth(self, now: datetime) -> dict[str, Any]:
        run = self._full_monitor_store.get_current() or self._full_monitor_store.get_latest()
        if run is None:
            return {"full_monitor_run_state": "DIAGNOSTIC_IDLE", "raw": {}}
        status = str(run.status or "UNKNOWN")
        last_seen = run.updated_at or run.ended_at or run.stopped_at or run.started_at
        freshness, _ = classify_freshness(last_seen, stale_after_seconds=300, now=now)
        if status in {"STARTING", "RUNNING", "STOPPING"} and freshness == ControlCenterFreshnessState.FRESH:
            state = "DIAGNOSTIC_RUNNING"
        elif freshness == ControlCenterFreshnessState.STALE:
            state = "DIAGNOSTIC_STALE"
        elif status in {"COMPLETED", "STOPPED"}:
            state = "DIAGNOSTIC_STOPPED"
        else:
            state = "DIAGNOSTIC_IDLE"
        return {"full_monitor_run_state": state, "raw": run.to_action_result()}

    def _db_truth(self, now: datetime, errors: list[str]) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"system_power_state": "UNKNOWN", "warnings": ["Database is not configured."]}
        try:
            with self._factory.connect() as conn:
                state = self._states.get_current_state(conn)
                system_power = state.system_power.value if state else "UNKNOWN"
                transition_at = state.system_power_transition_at if state else None
                last_cycle = _fetchone(
                    conn,
                    """
                    SELECT cycle_id,status,started_at,finished_at
                    FROM runtime_cycles_v2
                    WHERE status = 'COMPLETED'
                    ORDER BY finished_at DESC NULLS LAST, started_at DESC, id DESC
                    LIMIT 1
                    """,
                )
                cycle_count = _count_since(conn, "runtime_cycles_v2", "COALESCE(finished_at, started_at)", transition_at, "status = 'COMPLETED'")
                events_since = _count_since(conn, "event_log", "stored_at", transition_at)
                candidates_since = _count_since(conn, "paper_eligibility_candidates", "updated_at", transition_at)
                return {
                    "system_power_state": system_power,
                    "system_power_transition_at": _iso(transition_at),
                    "cycles_completed_since_system_on": cycle_count if system_power == "ON" else 0,
                    "last_cycle_id": (last_cycle or {}).get("cycle_id"),
                    "last_cycle_started_at": _iso((last_cycle or {}).get("started_at")),
                    "last_cycle_completed_at": _iso((last_cycle or {}).get("finished_at")),
                    "last_cycle_age_seconds": _age_seconds((last_cycle or {}).get("finished_at") or (last_cycle or {}).get("started_at"), now),
                    "events_since_system_on": events_since if system_power == "ON" else 0,
                    "candidates_updated_since_system_on": candidates_since if system_power == "ON" else 0,
                    "paper_intents": _count_table(conn, "paper_intents"),
                    "paper_orders": _count_table(conn, "paper_orders"),
                    "paper_fills": _count_table(conn, "paper_fills"),
                    "paper_positions": _count_table(conn, "paper_positions"),
                    "paper_position_closes": _count_table(conn, "paper_position_closes"),
                    "live_orders": _count_table(conn, "live_orders"),
                    "orders_v2": _count_table(conn, "orders_v2"),
                    "fills_v2": _count_table(conn, "fills_v2"),
                    "positions": _count_table(conn, "positions"),
                    "warnings": [],
                }
        except Exception as exc:
            errors.append(f"Supervisor life path DB query failed: {type(exc).__name__}: {exc}")
            return {"system_power_state": "UNKNOWN", "warnings": ["Supervisor life path DB query failed."]}

    def _cycle_state(self, supervisor: dict[str, Any], db_truth: dict[str, Any], system_power: str) -> str:
        current = str(supervisor.get("current_cycle_status") or "").upper()
        if current == "RUNNING":
            return "CYCLE_RUNNING"
        if current == "ERROR":
            return "CYCLE_FAILED"
        if current == "COMPLETED" or int(supervisor.get("cycles_completed") or 0) > 0:
            return "CYCLE_COMPLETED"
        if system_power == "ON" and int(db_truth.get("cycles_completed_since_system_on") or 0) > 0:
            return "CYCLE_COMPLETED"
        if system_power == "ON" and supervisor.get("supervisor_state") in {"ALIVE", "PARTIAL"}:
            return "CYCLE_CREATED"
        if system_power == "OFF":
            return "CYCLE_BLOCKED"
        return "UNKNOWN"

    def _life_state(self, *, system_power: str, supervisor_state: str, cycle_state: str, supervisor_freshness: str, blockers: list[str]) -> str:
        if system_power == "OFF":
            return "STOPPED"
        if supervisor_freshness == ControlCenterFreshnessState.STALE.value:
            return "STALE"
        if supervisor_state == "ALIVE" and cycle_state in {"CYCLE_COMPLETED", "CYCLE_RUNNING", "CYCLE_CREATED"}:
            return "ALIVE"
        if supervisor_state == "PARTIAL" or cycle_state == "CYCLE_FAILED":
            return "PARTIAL"
        if blockers:
            return "BLOCKED"
        return "UNKNOWN"

    def _freshness(self, supervisor: dict[str, Any], db_truth: dict[str, Any]) -> ControlCenterFreshnessState:
        if supervisor.get("freshness_state") == ControlCenterFreshnessState.FRESH.value:
            return ControlCenterFreshnessState.FRESH
        if supervisor.get("freshness_state") == ControlCenterFreshnessState.STALE.value:
            return ControlCenterFreshnessState.STALE
        if db_truth.get("last_cycle_completed_at"):
            return ControlCenterFreshnessState.STALE
        return ControlCenterFreshnessState.MISSING


def _status_for_life(life: str) -> ControlCenterStatus:
    if life == "ALIVE":
        return ControlCenterStatus.REAL
    if life == "PARTIAL":
        return ControlCenterStatus.PARTIAL
    if life == "STALE":
        return ControlCenterStatus.STALE
    if life in {"BLOCKED", "STOPPED"}:
        return ControlCenterStatus.LOCKED
    return ControlCenterStatus.MISSING


def _readiness_for_life(life: str) -> ControlCenterReadinessState:
    if life == "ALIVE":
        return ControlCenterReadinessState.READY
    if life == "PARTIAL":
        return ControlCenterReadinessState.PARTIAL
    if life in {"BLOCKED", "STOPPED", "STALE"}:
        return ControlCenterReadinessState.BLOCKED
    return ControlCenterReadinessState.UNKNOWN


def _runtime_state_for_life(life: str) -> ControlCenterRuntimeState:
    if life == "ALIVE":
        return ControlCenterRuntimeState.RUNNING
    if life == "PARTIAL":
        return ControlCenterRuntimeState.BLOCKED
    if life == "STALE":
        return ControlCenterRuntimeState.STALE
    if life == "STOPPED":
        return ControlCenterRuntimeState.STOPPED
    if life == "BLOCKED":
        return ControlCenterRuntimeState.BLOCKED
    return ControlCenterRuntimeState.UNKNOWN


def _compact_runtime(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_life_state": payload.get("runtime_life_state"),
        "system_power_state": payload.get("system_power_state"),
        "scheduler_state": payload.get("scheduler_state"),
        "supervisor_state": payload.get("supervisor_state"),
        "blockers": payload.get("blockers", []),
    }


def _compact_paper(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "paper_readiness_state": payload.get("paper_readiness_state"),
        "paper_execution_readiness_state": payload.get("paper_execution_readiness_state"),
        "paper_simulation_state": payload.get("paper_simulation_state"),
        "blockers": payload.get("blockers", []),
        "last_updated": payload.get("last_updated"),
    }


def _count_since(conn: Any, table: str, column: str, since: Any, extra_where: str | None = None) -> int:
    if since is None or not _table_exists(conn, table):
        return 0
    where = f"{column} >= %s"
    if extra_where:
        where = f"{where} AND {extra_where}"
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", (since,)).fetchone()
    return int(row["count"] or 0)


def _count_table(conn: Any, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return int(row["count"] or 0)


def _fetchone(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def _positive(value: Any) -> bool:
    try:
        return int(value or 0) > 0
    except Exception:
        return False


def _age_seconds(value: Any, now: datetime) -> float | None:
    parsed = _timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.isoformat() if parsed else None


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output
