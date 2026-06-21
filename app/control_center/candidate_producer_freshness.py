from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.control_center.paper_readiness import PaperReadinessService
from app.control_center.runtime_readiness import RuntimeReadinessService
from app.control_center.supervisor_life_path import SupervisorLifePathService
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
from app.repositories.runtime_state_repository import RuntimeStateRepository


CANDIDATE_FRESH_SECONDS = 300

SOURCE_MAP = {
    "system_power": "system_state.system_power + system_power_transition_at",
    "supervisor_life_path": "/dashboard/api/v2/control/supervisor-life-path",
    "runtime_readiness": "/dashboard/api/v2/control/runtime-readiness",
    "paper_readiness": "/dashboard/api/v2/control/paper-readiness",
    "runtime_cycles": "runtime_cycles_v2",
    "market_refresh": "runtime_cycles_v2 metadata source=market_service.refresh",
    "market_snapshots": "market_snapshots.captured_at + market_snapshots_v2.snapshot_at",
    "paper_eligibility_candidates": "paper_eligibility_candidates.updated_at",
    "paper_eligibility_runs": "paper_eligibility_runs.finished_at",
    "candidate_explanations": "derived from paper_eligibility_candidates.updated_at",
    "eligible_intent_bridge": "derived from ELIGIBLE paper_eligibility_candidates.updated_at",
    "no_trade": "no_trade_log.updated_at",
}


class CandidateProducerFreshnessService:
    """Read-only proof that SYSTEM ON is feeding candidate/readiness freshness."""

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        supervisor_life_path: SupervisorLifePathService | None = None,
        runtime_readiness: RuntimeReadinessService | None = None,
        paper_readiness: PaperReadinessService | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._states = RuntimeStateRepository()
        self._supervisor_life = supervisor_life_path or SupervisorLifePathService(connection_factory=self._factory)
        self._runtime_readiness = runtime_readiness or RuntimeReadinessService(connection_factory=self._factory)
        self._paper_readiness = paper_readiness or PaperReadinessService(connection_factory=self._factory)

    def get_freshness(self) -> dict[str, Any]:
        now = datetime.now(UTC)
        warnings: list[str] = []
        errors: list[str] = []
        blockers: list[str] = []
        db = self._db_truth(now, errors)
        supervisor = self._safe_supervisor(errors)
        runtime = self._safe_runtime(errors)
        paper = self._safe_paper(errors)

        system_power = db.get("system_power_state") or runtime.get("system_power_state") or supervisor.get("system_power_state") or "UNKNOWN"
        runtime_life = runtime.get("runtime_life_state") or supervisor.get("runtime_life_state") or "UNKNOWN"
        supervisor_life = supervisor.get("supervisor_life_state") or "UNKNOWN"
        system_on_at = db.get("last_system_on_at")
        updated = {
            "market_refresh": _after(db.get("last_market_refresh_at"), system_on_at),
            "market_snapshots": _after(db.get("last_market_snapshot_at"), system_on_at),
            "candidates": _after(db.get("last_candidate_updated_at"), system_on_at),
            "candidate_explanations": _after(db.get("last_candidate_explanation_updated_at"), system_on_at),
            "eligible_bridge": _after(db.get("last_eligible_bridge_updated_at"), system_on_at),
            "paper_readiness": _after(paper.get("last_updated") or paper.get("generated_at"), system_on_at),
        }

        candidate_freshness, candidate_age = classify_freshness(db.get("last_candidate_updated_at"), stale_after_seconds=CANDIDATE_FRESH_SECONDS, now=now)
        candidate_update_result = self._candidate_update_result(db, updated, system_power, supervisor_life)
        candidate_producer_state = self._producer_state(system_power, supervisor_life, candidate_freshness, candidate_update_result)
        supervisor_path_result = self._supervisor_path_result(supervisor_life, candidate_update_result, updated)

        if system_power == "OFF":
            blockers.append("SYSTEM_POWER_OFF")
        if supervisor_life in {"STOPPED", "BLOCKED", "STALE", "UNKNOWN"}:
            blockers.append(f"SUPERVISOR_{supervisor_life}")
        if candidate_update_result == "CANDIDATES_BLOCKED_BY_RUNTIME":
            blockers.append("CANDIDATES_BLOCKED_BY_RUNTIME")
        if candidate_update_result == "CANDIDATES_BLOCKED_BY_SOURCE":
            blockers.append("CANDIDATES_BLOCKED_BY_SOURCE")
        if candidate_update_result == "CANDIDATES_NOT_UPDATED_WITH_REASON":
            blockers.append("CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON")
        if candidate_freshness == ControlCenterFreshnessState.STALE:
            blockers.append("CANDIDATE_LEDGER_STALE")
        if candidate_freshness == ControlCenterFreshnessState.MISSING:
            blockers.append("CANDIDATE_LEDGER_MISSING")

        if not updated["market_refresh"] and system_power == "ON":
            warnings.append("MARKET_REFRESH_NOT_UPDATED_SINCE_SYSTEM_ON")
        if not updated["market_snapshots"] and system_power == "ON":
            warnings.append("MARKET_SNAPSHOTS_NOT_UPDATED_SINCE_SYSTEM_ON")
        if not updated["candidates"] and system_power == "ON":
            warnings.append("CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON")
        if paper.get("paper_simulation_state") == "OFF":
            warnings.append("PAPER_SIMULATION_OFF")

        freshness_state = candidate_freshness.value if candidate_freshness in {ControlCenterFreshnessState.FRESH, ControlCenterFreshnessState.STALE} else ControlCenterFreshnessState.MISSING.value
        readiness_state = "READY" if candidate_producer_state == "RUNNING" else "BLOCKED" if candidate_producer_state in {"BLOCKED", "STALE", "STOPPED"} else "UNKNOWN"
        status = ControlCenterStatus.REAL if candidate_producer_state == "RUNNING" else ControlCenterStatus.STALE if candidate_producer_state == "STALE" else ControlCenterStatus.LOCKED if blockers else ControlCenterStatus.MISSING

        payload = {
            "candidate_producer_state": candidate_producer_state,
            "candidate_freshness_state": "FRESH" if candidate_freshness == ControlCenterFreshnessState.FRESH else "STALE" if candidate_freshness == ControlCenterFreshnessState.STALE else "MISSING" if candidate_freshness == ControlCenterFreshnessState.MISSING else "UNKNOWN",
            "candidate_update_result": candidate_update_result,
            "supervisor_candidate_path_result": supervisor_path_result,
            "system_power_state": system_power,
            "runtime_life_state": runtime_life,
            "supervisor_life_state": supervisor_life,
            "last_system_on_at": system_on_at,
            "last_supervisor_cycle_at": supervisor.get("last_cycle_completed_at") or supervisor.get("supervisor_last_heartbeat"),
            "last_market_refresh_at": db.get("last_market_refresh_at"),
            "last_market_snapshot_at": db.get("last_market_snapshot_at"),
            "last_candidate_updated_at": db.get("last_candidate_updated_at"),
            "last_candidate_explanation_updated_at": db.get("last_candidate_explanation_updated_at"),
            "last_eligible_bridge_updated_at": db.get("last_eligible_bridge_updated_at"),
            "last_no_trade_updated_at": db.get("last_no_trade_updated_at"),
            "last_paper_readiness_updated_at": paper.get("last_updated") or paper.get("generated_at"),
            "updated_after_system_on": updated,
            "counts_before_after_available": bool(system_on_at),
            "blockers": _unique(blockers),
            "warnings": _unique(warnings + list(db.get("warnings") or [])),
            "errors": _unique(errors),
            "source": SOURCE_MAP,
            "last_updated": now.isoformat(),
            "counts": {
                "candidates_total": db.get("candidates_total", 0),
                "candidates_updated_since_system_on": db.get("candidates_updated_since_system_on", 0),
                "eligible_candidates": db.get("eligible_candidates", 0),
                "candidate_runs_since_system_on": db.get("candidate_runs_since_system_on", 0),
                "runtime_cycles_since_system_on": db.get("runtime_cycles_since_system_on", 0),
                "market_snapshots_since_system_on": db.get("market_snapshots_since_system_on", 0),
                "no_trade_updated_since_system_on": db.get("no_trade_updated_since_system_on", 0),
            },
            "runtime_readiness": {
                "runtime_life_state": runtime_life,
                "readiness_state": runtime.get("readiness_state"),
                "blockers": runtime.get("blockers", []),
            },
            "paper_readiness": {
                "paper_readiness_state": paper.get("paper_readiness_state"),
                "paper_simulation_state": paper.get("paper_simulation_state"),
                "readiness_state": paper.get("readiness_state"),
                "blockers": paper.get("blockers", []),
            },
        }
        envelope = truth_envelope(
            status=status,
            source="candidate producer freshness: system_state + runtime supervisor + candidate/market/readiness tables",
            truth_state=truth_from_freshness(ControlCenterFreshnessState(freshness_state), has_history=bool(db.get("last_candidate_updated_at"))),
            data=payload,
            last_updated=payload["last_candidate_updated_at"] or payload["last_updated"],
            stale_after_seconds=CANDIDATE_FRESH_SECONDS,
            age_seconds=candidate_age,
            freshness_state=ControlCenterFreshnessState(freshness_state),
            runtime_state=ControlCenterRuntimeState.RUNNING if candidate_producer_state == "RUNNING" else ControlCenterRuntimeState.BLOCKED if candidate_producer_state == "BLOCKED" else ControlCenterRuntimeState.STOPPED if candidate_producer_state == "STOPPED" else ControlCenterRuntimeState.STALE if candidate_producer_state == "STALE" else ControlCenterRuntimeState.UNKNOWN,
            readiness_state=ControlCenterReadinessState.READY if readiness_state == "READY" else ControlCenterReadinessState.BLOCKED if readiness_state == "BLOCKED" else ControlCenterReadinessState.UNKNOWN,
            warnings=payload["warnings"],
            errors=payload["errors"],
        ).to_dict()
        return {**envelope, **payload, "readiness_state": readiness_state, "freshness_state": freshness_state}

    def _safe_supervisor(self, errors: list[str]) -> dict[str, Any]:
        try:
            return self._supervisor_life.get_life_path()
        except Exception as exc:
            errors.append(f"Supervisor life path unavailable: {type(exc).__name__}: {exc}")
            return {}

    def _safe_runtime(self, errors: list[str]) -> dict[str, Any]:
        try:
            return self._runtime_readiness.get_readiness()
        except Exception as exc:
            errors.append(f"Runtime readiness unavailable: {type(exc).__name__}: {exc}")
            return {}

    def _safe_paper(self, errors: list[str]) -> dict[str, Any]:
        try:
            return self._paper_readiness.get_readiness()
        except Exception as exc:
            errors.append(f"Paper readiness unavailable: {type(exc).__name__}: {exc}")
            return {}

    def _db_truth(self, now: datetime, errors: list[str]) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"system_power_state": "UNKNOWN", "warnings": ["Database is not configured."]}
        try:
            with self._factory.connect() as conn:
                state = self._states.get_current_state(conn)
                system_power = state.system_power.value if state else "UNKNOWN"
                system_on_at = state.system_power_transition_at if state and system_power == "ON" else None
                latest_candidate = _max_ts(conn, "paper_eligibility_candidates", "COALESCE(updated_at, created_at)")
                latest_eligible = _max_ts(conn, "paper_eligibility_candidates", "COALESCE(updated_at, created_at)", "status = 'ELIGIBLE'")
                latest_candidate_run = _max_ts(conn, "paper_eligibility_runs", "COALESCE(finished_at, started_at)")
                latest_no_trade = _max_ts(conn, "no_trade_log", "COALESCE(updated_at, created_at)")
                latest_market_snapshot = max_ts([_max_ts(conn, "market_snapshots", "captured_at"), _max_ts(conn, "market_snapshots_v2", "snapshot_at")])
                latest_market_refresh = _fetch_scalar(
                    conn,
                    """
                    SELECT MAX(COALESCE(finished_at, started_at)) AS ts
                    FROM runtime_cycles_v2
                    WHERE metadata_json->>'source' = 'market_service.refresh'
                    """,
                ) if _table_exists(conn, "runtime_cycles_v2") else None
                latest_supervisor_cycle = _fetch_scalar(
                    conn,
                    """
                    SELECT MAX(COALESCE(finished_at, started_at)) AS ts
                    FROM runtime_cycles_v2
                    WHERE metadata_json->>'source' = 'runtime_supervisor'
                    """,
                ) if _table_exists(conn, "runtime_cycles_v2") else None
                return {
                    "system_power_state": system_power,
                    "last_system_on_at": _iso(system_on_at),
                    "last_market_refresh_at": _iso(latest_market_refresh),
                    "last_market_snapshot_at": _iso(latest_market_snapshot),
                    "last_candidate_updated_at": _iso(latest_candidate),
                    "last_candidate_explanation_updated_at": _iso(latest_candidate),
                    "last_eligible_bridge_updated_at": _iso(latest_eligible),
                    "last_no_trade_updated_at": _iso(latest_no_trade),
                    "last_candidate_run_at": _iso(latest_candidate_run),
                    "last_supervisor_runtime_cycle_at": _iso(latest_supervisor_cycle),
                    "candidates_total": _count(conn, "paper_eligibility_candidates"),
                    "eligible_candidates": _count(conn, "paper_eligibility_candidates", "status = 'ELIGIBLE'"),
                    "candidates_updated_since_system_on": _count_since(conn, "paper_eligibility_candidates", "COALESCE(updated_at, created_at)", system_on_at),
                    "candidate_runs_since_system_on": _count_since(conn, "paper_eligibility_runs", "COALESCE(finished_at, started_at)", system_on_at),
                    "runtime_cycles_since_system_on": _count_since(conn, "runtime_cycles_v2", "COALESCE(finished_at, started_at)", system_on_at, "metadata_json->>'source' = 'runtime_supervisor'"),
                    "market_snapshots_since_system_on": _count_since(conn, "market_snapshots", "captured_at", system_on_at) + _count_since(conn, "market_snapshots_v2", "snapshot_at", system_on_at),
                    "no_trade_updated_since_system_on": _count_since(conn, "no_trade_log", "COALESCE(updated_at, created_at)", system_on_at),
                    "warnings": [],
                }
        except Exception as exc:
            errors.append(f"Candidate producer freshness DB query failed: {type(exc).__name__}: {exc}")
            return {"system_power_state": "UNKNOWN", "warnings": ["Candidate producer freshness DB query failed."]}

    def _candidate_update_result(self, db: dict[str, Any], updated: dict[str, bool], system_power: str, supervisor_life: str) -> str:
        if system_power != "ON":
            return "CANDIDATES_BLOCKED_BY_RUNTIME"
        if supervisor_life in {"STOPPED", "BLOCKED", "STALE", "UNKNOWN"}:
            return "CANDIDATES_BLOCKED_BY_RUNTIME"
        if _int(db.get("candidates_updated_since_system_on")) > 0:
            return "CANDIDATES_UPDATED"
        if _int(db.get("candidates_total")) == 0:
            return "NO_CANDIDATES_FOUND"
        if _int(db.get("candidate_runs_since_system_on")) > 0:
            return "CANDIDATES_NOT_UPDATED_WITH_REASON"
        return "CANDIDATES_BLOCKED_BY_SOURCE"

    def _producer_state(self, system_power: str, supervisor_life: str, freshness: ControlCenterFreshnessState, result: str) -> str:
        if system_power == "OFF":
            return "STOPPED"
        if result == "CANDIDATES_UPDATED" and freshness == ControlCenterFreshnessState.FRESH:
            return "RUNNING"
        if result in {"CANDIDATES_BLOCKED_BY_RUNTIME", "CANDIDATES_BLOCKED_BY_SOURCE", "CANDIDATES_NOT_UPDATED_WITH_REASON"}:
            return "BLOCKED"
        if freshness == ControlCenterFreshnessState.STALE:
            return "STALE"
        if freshness == ControlCenterFreshnessState.MISSING:
            return "MISSING"
        if supervisor_life == "ALIVE":
            return "BLOCKED"
        return "UNKNOWN"

    def _supervisor_path_result(self, supervisor_life: str, result: str, updated: dict[str, bool]) -> str:
        if supervisor_life != "ALIVE":
            return "FAILED" if supervisor_life in {"STOPPED", "BLOCKED"} else "UNKNOWN"
        if result == "CANDIDATES_UPDATED":
            return "PASSED"
        if result in {"CANDIDATES_NOT_UPDATED_WITH_REASON", "CANDIDATES_BLOCKED_BY_SOURCE"}:
            return "PARTIAL"
        return "FAILED"


def _count_since(conn: Any, table: str, column: str, since: Any, extra_where: str | None = None) -> int:
    if since is None or not _table_exists(conn, table):
        return 0
    where = f"{column} >= %s"
    if extra_where:
        where = f"{where} AND {extra_where}"
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE {where}", (_timestamp(since),)).fetchone()
    return int(row["count"] or 0)


def _count(conn: Any, table: str, where: str | None = None) -> int:
    if not _table_exists(conn, table):
        return 0
    sql = f"SELECT COUNT(*) AS count FROM {table}"
    if where:
        sql = f"{sql} WHERE {where}"
    return int(conn.execute(sql).fetchone()["count"] or 0)


def _max_ts(conn: Any, table: str, column: str, where: str | None = None) -> Any:
    if not _table_exists(conn, table):
        return None
    sql = f"SELECT MAX({column}) AS ts FROM {table}"
    if where:
        sql = f"{sql} WHERE {where}"
    return _fetch_scalar(conn, sql)


def _fetch_scalar(conn: Any, sql: str) -> Any:
    row = conn.execute(sql).fetchone()
    return row["ts"] if row else None


def _table_exists(conn: Any, table: str) -> bool:
    row = conn.execute("SELECT to_regclass(%s) AS table_name", (table,)).fetchone()
    return bool(row and row["table_name"])


def max_ts(values: list[Any]) -> Any:
    parsed = [_timestamp(value) for value in values if _timestamp(value) is not None]
    return max(parsed) if parsed else None


def _after(value: Any, since: Any) -> bool:
    parsed_value = _timestamp(value)
    parsed_since = _timestamp(since)
    if parsed_value is None or parsed_since is None:
        return False
    return parsed_value >= parsed_since


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


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in output:
            output.append(text)
    return output
