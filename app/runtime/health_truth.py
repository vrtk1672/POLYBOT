from __future__ import annotations

import os
import socket
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from app.db.connection import DatabaseConnectionFactory
from app.repositories.runtime_cycle_repository import RuntimeCycleRepository
from app.repositories.runtime_state_repository import RuntimeStateRepository
from app.repositories.service_health_repository import ServiceHealthRepository
from app.control_center.truth_hardening import classify_freshness, truth_from_freshness
from app.control_center.truth_contract import ControlCenterFreshnessState
from app.runtime.modes import RuntimeMode
from app.runtime.system_power import SystemPower


class HealthTruthService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._states = RuntimeStateRepository()
        self._cycles = RuntimeCycleRepository()
        self._services = ServiceHealthRepository()

    def get_health_truth(self) -> dict[str, object]:
        warnings: list[str] = []
        if not self._factory.enabled:
            return {
                "overall_status": "ERROR",
                "current_mode": None,
                "kill_switch_active": True,
                "cooldown_active": False,
                "attack_mode_active": False,
                "active_cycle": None,
                "services": [],
                "stale_services": [],
                "critical_incidents": [],
                "last_mode_transition": None,
                "last_successful_cycle": None,
                "warnings": ["runtime database is unavailable; fail-safe active"],
            }
        try:
            redis_health = _check_redis_health(os.getenv("REDIS_URL"))
            with self._factory.connect() as conn:
                with conn.transaction():
                    self._refresh_process_and_dependency_health(conn, redis_health)
                state = self._states.get_current_state(conn)
                with conn.transaction():
                    cutoff = datetime.now(UTC) - timedelta(seconds=600)
                    self._cycles.mark_stale_abandoned(conn, older_than=cutoff, reason="runtime_health_ttl_cleanup")
                    if state is not None and state.system_power == SystemPower.OFF:
                        self._cycles.mark_open_cycles_safe_stopped(conn, reason="runtime_health_system_off_cleanup")
                services = [dict(row) for row in self._services.list_services(conn)]
                active_cycle = self._cycles.get_current_cycle(conn)
                recent_cycles = self._cycles.get_recent_cycles(conn, 20)
                history = self._states.list_history(conn, 1)
                critical_incidents = conn.execute(
                    """
                    SELECT *
                    FROM runtime_incidents
                    WHERE status = 'OPEN' AND severity IN ('CRITICAL', 'HIGH')
                    ORDER BY last_seen_at DESC, id DESC
                    LIMIT 20
                    """
                ).fetchall()
        except Exception as exc:
            return {
                "overall_status": "ERROR",
                "current_mode": None,
                "kill_switch_active": True,
                "cooldown_active": False,
                "attack_mode_active": False,
                "active_cycle": None,
                "services": [],
                "stale_services": [],
                "critical_incidents": [],
                "last_mode_transition": None,
                "last_successful_cycle": None,
                "warnings": [f"runtime database health query failed: {exc}"],
            }
        if state is None:
            return {
                "overall_status": "ERROR",
                "current_mode": None,
                "kill_switch_active": True,
                "cooldown_active": False,
                "attack_mode_active": False,
                "active_cycle": _json_safe(active_cycle),
                "services": [_json_safe(row) for row in services],
                "stale_services": [],
                "critical_incidents": [_json_safe(row) for row in critical_incidents],
                "last_mode_transition": None,
                "last_successful_cycle": None,
                "warnings": ["runtime state is missing; fail-safe active"],
            }
        stale_services = _stale_services(services)
        if stale_services:
            warnings.append("one or more services are stale")
        if state.system_power == SystemPower.OFF:
            overall = "SAFE_STOPPED"
            warnings.append("system power is OFF; autonomous runtime work is blocked")
        elif state.current_mode == RuntimeMode.KILL or state.kill_switch_active:
            overall = "SAFE_STOPPED"
        elif (
            critical_incidents
            or stale_services
            or any(str(row["status"]) in {"ERROR", "DEGRADED", "STALE"} for row in services)
        ):
            overall = "DEGRADED"
        else:
            overall = "HEALTHY"
        last_success = next(
            (row for row in recent_cycles if str(row.get("status")) == "COMPLETED"),
            None,
        )
        active_cycle_truth = _cycle_truth(active_cycle, stale_after_seconds=600)
        last_success_truth = _cycle_truth(last_success, stale_after_seconds=600)
        if active_cycle_truth.get("freshness_state") == "STALE":
            warnings.append("active runtime cycle row is stale; treating it as last-known runtime truth")
        payload = {
            "overall_status": overall,
            "source": "runtime_state + runtime_cycles_v2 + service_health",
            "freshness_state": last_success_truth.get("freshness_state"),
            "truth_state": last_success_truth.get("truth_state"),
            "readiness_state": "BLOCKED" if overall == "SAFE_STOPPED" else ("PARTIAL" if overall == "DEGRADED" else "READY"),
            "runtime_state": "STOPPED" if overall == "SAFE_STOPPED" else ("STALE" if active_cycle_truth.get("freshness_state") == "STALE" else "RUNNING"),
            "current_mode": state.current_mode.value,
            "system_power": state.system_power.value,
            "runtime_work_allowed": state.system_power == SystemPower.ON,
            "kill_switch_active": state.kill_switch_active,
            "cooldown_active": state.cooldown_active,
            "attack_mode_active": state.attack_mode_active,
            "active_cycle": _json_safe(active_cycle),
            "active_cycle_truth": _json_safe(active_cycle_truth),
            "services": [_json_safe(row) for row in services],
            "stale_services": [_json_safe(row) for row in stale_services],
            "critical_incidents": [_json_safe(row) for row in critical_incidents],
            "last_mode_transition": _json_safe(history[0]) if history else None,
            "last_successful_cycle": _json_safe(last_success),
            "last_successful_cycle_truth": _json_safe(last_success_truth),
            "warnings": warnings,
        }
        try:
            from app.control_center.runtime_readiness import RuntimeReadinessService

            readiness = RuntimeReadinessService(connection_factory=self._factory).get_readiness()
            payload.update(
                {
                    "runtime_life_state": readiness.get("runtime_life_state"),
                    "system_power_state": readiness.get("system_power_state"),
                    "scheduler_state": readiness.get("scheduler_state"),
                    "scheduler_blocked_reason": readiness.get("scheduler_blocked_reason"),
                    "supervisor_state": readiness.get("supervisor_state"),
                    "full_monitor_run_state": readiness.get("full_monitor_run_state"),
                    "readiness_blockers": readiness.get("blockers", []),
                    "runtime_readiness": readiness.get("data", readiness),
                }
            )
        except Exception as exc:
            payload["warnings"] = [*warnings, f"runtime readiness overlay failed: {type(exc).__name__}: {exc}"]
        return payload

    def _refresh_process_and_dependency_health(
        self,
        conn,
        redis_health: dict[str, object] | None,
    ) -> None:
        self._services.upsert_service_health(
            conn,
            service_name="fastapi",
            service_type="api",
            status="RUNNING",
            details={"health_source": "runtime_health_request"},
        )
        self._services.mark_heartbeat(conn, "fastapi", status="RUNNING")

        try:
            conn.execute("SELECT 1")
            self._services.upsert_service_health(
                conn,
                service_name="postgres",
                service_type="persistence",
                status="HEALTHY",
                details={"health_source": "runtime_health_request"},
            )
            self._services.mark_heartbeat(conn, "postgres", status="HEALTHY")
        except Exception as exc:
            self._services.upsert_service_health(
                conn,
                service_name="postgres",
                service_type="persistence",
                status="ERROR",
                details={"health_source": "runtime_health_request", "error": str(exc)},
            )
            self._services.mark_error(conn, "postgres", {"error": str(exc)})

        if redis_health is None:
            return
        redis_status = "HEALTHY" if redis_health.get("ok") is True else "ERROR"
        self._services.upsert_service_health(
            conn,
            service_name="redis",
            service_type="cache",
            status=redis_status,
            details={
                "health_source": "runtime_health_request",
                "configured": True,
                "host": redis_health.get("host"),
                "port": redis_health.get("port"),
                "error": redis_health.get("error"),
            },
        )
        if redis_status == "HEALTHY":
            self._services.mark_heartbeat(conn, "redis", status="HEALTHY")
        else:
            self._services.mark_error(conn, "redis", {"error": redis_health.get("error")})


def _stale_services(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    stale: list[dict[str, object]] = []
    for row in rows:
        heartbeat = row.get("last_heartbeat_at")
        if str(row.get("status")) == "STALE" or (heartbeat is not None and heartbeat < cutoff):
            stale.append(row)
    return stale


def _check_redis_health(redis_url: str | None) -> dict[str, object] | None:
    if not redis_url:
        return None
    parsed = urlparse(redis_url)
    host = parsed.hostname
    port = parsed.port or 6379
    if not host:
        return {"ok": False, "host": None, "port": port, "error": "REDIS_URL host is missing"}
    try:
        with socket.create_connection((host, port), timeout=1.0) as sock:
            sock.settimeout(1.0)
            sock.sendall(b"*1\r\n$4\r\nPING\r\n")
            response = sock.recv(16)
        if response.startswith(b"+PONG"):
            return {"ok": True, "host": host, "port": port, "error": None}
        return {
            "ok": False,
            "host": host,
            "port": port,
            "error": f"unexpected Redis PING response: {response!r}",
        }
    except OSError as exc:
        return {"ok": False, "host": host, "port": port, "error": str(exc)}


def _cycle_truth(row: dict[str, object] | None, *, stale_after_seconds: int) -> dict[str, object]:
    if not row:
        return {
            "source": "runtime_cycles_v2",
            "last_updated": None,
            "age_seconds": None,
            "freshness_state": "MISSING",
            "truth_state": "UNKNOWN",
            "runtime_state": "UNKNOWN",
            "readiness_state": "UNKNOWN",
            "warnings": ["No runtime cycle row is available."],
        }
    last_updated = row.get("finished_at") or row.get("started_at")
    freshness, age = classify_freshness(last_updated, stale_after_seconds=stale_after_seconds)
    runtime_state = "RUNNING" if str(row.get("status")) == "RUNNING" and freshness == ControlCenterFreshnessState.FRESH else "STALE"
    if str(row.get("status")) == "COMPLETED" and freshness == ControlCenterFreshnessState.FRESH:
        runtime_state = "STOPPED"
    return {
        "source": "runtime_cycles_v2",
        "cycle_id": row.get("cycle_id"),
        "cycle_status": row.get("status"),
        "last_updated": last_updated,
        "age_seconds": age,
        "freshness_state": freshness.value,
        "truth_state": truth_from_freshness(freshness, has_history=True).value,
        "runtime_state": runtime_state,
        "readiness_state": "READY" if freshness == ControlCenterFreshnessState.FRESH else "NOT_READY",
        "warnings": [] if freshness == ControlCenterFreshnessState.FRESH else ["Runtime cycle evidence is stale."],
    }


def _json_safe(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
