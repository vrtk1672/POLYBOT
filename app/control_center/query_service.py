from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.control_center.truth_contract import (
    ControlCenterFreshnessState,
    ControlCenterReadinessState,
    ControlCenterRuntimeState,
    ControlCenterStatus,
    ControlCenterTruthState,
    require_candidate_truth_state,
    require_decision_source,
    require_events_source,
    require_health_source,
    require_pnl_source,
    require_positions_source,
    require_runtime_status_source,
    truth_envelope,
)
from app.control_center.truth_hardening import (
    classify_freshness,
    classify_service_runtime,
    truth_from_freshness,
)
from app.db.connection import DatabaseConnectionFactory
from app.repositories.event_store_repository import EventStoreRepository
from app.services.ai_context_router import AIContextRouterService
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.paper_dashboard_truth import PaperDashboardTruthService
from app.services.paper_intents import PaperIntentGateService
from app.services.risk_evidence_mesh import RiskEvidenceMeshService
from app.services.truth_state import TruthStateService


DEFAULT_STALE_AFTER_SECONDS = 300
CONTROL_CENTER_ENDPOINTS = (
    "overview",
    "organs",
    "live-flow",
    "decision-xray",
    "blockers",
    "closest-actionable",
    "truth-state",
    "risk-evidence",
    "lifecycle-governance",
    "mesh-dialogues",
    "pnl-ledger",
    "positions",
    "no-trade",
    "ai",
    "logs",
    "runtime-readiness",
    "paper-readiness",
    "runtime-supervisor",
    "paper-simulation",
)


class ControlCenterQueryService:
    """Read-only Control Center API adapter.

    The service returns Stage 4 Truth Contract envelopes and never calls mutating
    services or runtime refresh paths.
    """

    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()

    def overview(self) -> dict[str, Any]:
        source = "runtime_state_service_health_event_log"
        try:
            require_runtime_status_source(source)
            if not self._factory.enabled:
                return self._missing(
                    source=source,
                    warnings=["Overview sources are unavailable because the database is not configured."],
                )
            data = self._read_overview()
            has_any_source = bool(data["source_counts"])
            status = ControlCenterStatus.PARTIAL if has_any_source else ControlCenterStatus.MISSING
            data = {
                **data,
                "control_endpoints": list(CONTROL_CENTER_ENDPOINTS),
                "read_only": True,
                "mutating_actions_exposed": [],
            }
            warnings = ["Overview uses read-only source counts only; Stage 5 does not claim full runtime status."]
            if not has_any_source:
                warnings.append("No overview source tables are available.")
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data=data,
                last_updated=data.get("latest_at") or data.get("generated_at"),
                warnings=warnings,
            )
        except Exception as exc:
            return self._error(source, exc)

    def organs(self) -> dict[str, Any]:
        source = "service_health_heartbeat"
        try:
            require_health_source(source)
            if not self._factory.enabled:
                return self._missing(
                    source=source,
                    warnings=["Service heartbeat source is unavailable because the database is not configured."],
                )
            data = self._read_service_health(limit=100)
            status = ControlCenterStatus.REAL if data["services"] else ControlCenterStatus.MISSING
            if data.get("stale_services"):
                status = ControlCenterStatus.STALE
            elif data.get("registered_only_services"):
                status = ControlCenterStatus.PARTIAL
            truth_state = self._truth_state_for_status(status)
            warnings = [] if data["services"] else ["No service_health heartbeat rows are available."]
            if data.get("registered_only_services"):
                warnings.append("Registered services are not treated as running until heartbeat or success evidence exists.")
            if data.get("stale_services"):
                warnings.append("One or more services have stale heartbeat/success evidence.")
            return self._envelope(
                status=status,
                source=source,
                truth_state=truth_state,
                data=data,
                last_updated=data.get("latest_heartbeat_at") or data.get("generated_at"),
                runtime_state=ControlCenterRuntimeState.STALE if data.get("stale_services") else None,
                readiness_state=ControlCenterReadinessState.PARTIAL if data.get("registered_only_services") else None,
                warnings=warnings,
            )
        except Exception as exc:
            return self._error(source, exc)

    def live_flow(self) -> dict[str, Any]:
        source = "event_log"
        try:
            require_events_source(source)
            if not self._factory.enabled:
                return self._missing(
                    source=source,
                    warnings=["Event source is unavailable because the database is not configured."],
                )
            with self._factory.connect() as conn:
                if not self._table_exists(conn, "event_log"):
                    return self._missing(source=source, warnings=["event_log table is not available."])
                events = EventStoreRepository().list_recent_events(conn, limit=50)
            data = {"events": self._json_safe(events), "count": len(events), "read_only": True}
            return self._envelope(
                status=ControlCenterStatus.REAL if events else ControlCenterStatus.MISSING,
                source=source,
                truth_state=ControlCenterTruthState.ACTIVE_FRESH if events else ControlCenterTruthState.UNKNOWN,
                data=data,
                last_updated=self._latest_timestamp(events, ("stored_at", "occurred_at")),
                warnings=[] if events else ["No recent event_log rows are available."],
            )
        except Exception as exc:
            return self._error(source, exc)

    def decision_xray(self) -> dict[str, Any]:
        source = "risk_evidence_mesh_source"
        try:
            require_decision_source(source)
            payload = self._service_payload(lambda: RiskEvidenceMeshService(connection_factory=self._factory).dashboard_summary(limit=20))
            status = self._payload_status(payload)
            data = {
                "risk_evidence": payload,
                "decision_visibility": "read_only",
                "approval_claimed": False,
            }
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data=data,
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "Decision X-Ray is partial until unified evidence bundles are complete."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def blockers(self) -> dict[str, Any]:
        source = "no_trade_log_risk_evidence_mesh"
        try:
            no_trade = self._service_payload(lambda: PaperIntentGateService(connection_factory=self._factory).get_no_trade_dashboard_summary(limit=50))
            risk = self._service_payload(lambda: RiskEvidenceMeshService(connection_factory=self._factory).dashboard_summary(limit=50))
            status = self._combined_status([self._payload_status(no_trade), self._payload_status(risk)])
            payload = {"no_trade": no_trade, "risk_evidence": risk}
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"blockers": payload, "read_only": True},
                last_updated=self._timestamp_from_payload(payload),
                warnings=[
                    *self._warnings_for_payload(no_trade, "No-trade blocker summary is missing or partial."),
                    *self._warnings_for_payload(risk, "Risk-evidence blocker summary is missing or partial."),
                    "Unified blocker source is partial; no-trade and risk-evidence summaries are reused.",
                ],
            )
        except Exception as exc:
            return self._error(source, exc)

    def closest_actionable(self) -> dict[str, Any]:
        source = "risk_evidence_mesh_candidates"
        try:
            payload = self._service_payload(lambda: RiskEvidenceMeshService(connection_factory=self._factory).dashboard_summary(limit=20))
            candidates = list(payload.get("closest_to_actionable_risk_subjects") or [])
            normalized_candidates = []
            for candidate in candidates:
                item = self._safe_dict(candidate)
                item.setdefault("truth_state", self._truth_state_from_candidate(item))
                require_candidate_truth_state(item["truth_state"])
                normalized_candidates.append(item)
            status = self._payload_status(payload)
            if not normalized_candidates:
                status = ControlCenterStatus.PARTIAL
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"candidates": normalized_candidates, "count": len(normalized_candidates), "read_only": True},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "No closest-actionable candidates with full truth_state are available yet."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def truth_state(self) -> dict[str, Any]:
        source = "truth_state_registry"
        try:
            payload = self._service_payload(lambda: TruthStateService(connection_factory=self._factory).dashboard_summary(limit=50))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data=payload,
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "Truth-state registry is unavailable or incomplete."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def risk_evidence(self) -> dict[str, Any]:
        source = "risk_evidence_mesh_evaluations"
        try:
            payload = self._service_payload(lambda: RiskEvidenceMeshService(connection_factory=self._factory).dashboard_summary(limit=50))
            status = self._payload_status(payload)
            data = {"risk_evidence": payload, "risk_gate_bypassed": False, "approval_claimed": False}
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data=data,
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "Risk evidence is read-only and does not claim approval."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def lifecycle_governance(self) -> dict[str, Any]:
        source = "lifecycle_governance"
        try:
            payload = self._service_payload(lambda: LifecycleGovernanceGateService(connection_factory=self._factory).dashboard_summary(limit=50))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"lifecycle_governance": payload, "read_only": True, "actions_triggered": []},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "Lifecycle governance view is read-only; no lifecycle changes are triggered."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def mesh_dialogues(self) -> dict[str, Any]:
        source = "brain_dialogue_events"
        try:
            if not self._factory.enabled:
                return self._missing(
                    source=source,
                    warnings=["Brain/mesh dialogue source is unavailable because the database is not configured."],
                )
            payload = self._read_brain_dialogue(limit=50)
            status = ControlCenterStatus.REAL if payload["events"] else ControlCenterStatus.MISSING
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"mesh_dialogues": payload, "dialogue_invented": False},
                last_updated=self._timestamp_from_payload(payload),
                warnings=[] if payload["events"] else ["True brain/mesh dialogue events are absent; no dialogue is invented."],
            )
        except Exception as exc:
            return self._error(source, exc)

    def pnl_ledger(self) -> dict[str, Any]:
        source = "paper_pnl_ledger"
        try:
            require_pnl_source(source)
            payload = self._service_payload(lambda: PaperDashboardTruthService(connection_factory=self._factory).get_pnl(limit=30))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"pnl_ledger": payload, "fake_pnl": False},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "PnL requires paper_daily_pnl/paper ledger source; no fake PnL is supplied."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def positions(self) -> dict[str, Any]:
        source = "paper_positions"
        try:
            require_positions_source(source)
            payload = self._service_payload(lambda: PaperDashboardTruthService(connection_factory=self._factory).get_positions(limit=100))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"positions": payload, "fake_positions": False},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "Positions require canonical paper_positions source."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def no_trade(self) -> dict[str, Any]:
        source = "no_trade_log"
        try:
            payload = self._service_payload(lambda: PaperIntentGateService(connection_factory=self._factory).get_no_trade_dashboard_summary(limit=50))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"no_trade": payload, "first_class_decision": True},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "No-trade visibility reuses paper intent/no_trade summaries."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def ai(self) -> dict[str, Any]:
        source = "ai_context_router"
        try:
            payload = self._service_payload(lambda: AIContextRouterService(connection_factory=self._factory).dashboard_summary(limit=20))
            status = self._payload_status(payload)
            return self._envelope(
                status=status,
                source=source,
                truth_state=self._truth_state_for_status(status),
                data={"ai": payload, "execution_authority": False, "interpretation_only": True},
                last_updated=self._timestamp_from_payload(payload),
                warnings=self._warnings_for_payload(payload, "AI is interpretation-only and cannot execute trades."),
            )
        except Exception as exc:
            return self._error(source, exc)

    def logs(self) -> dict[str, Any]:
        source = "runtime_incidents_event_log_dlq"
        try:
            if not self._factory.enabled:
                return self._missing(
                    source=source,
                    warnings=["Log-like sources are unavailable because the database is not configured."],
                )
            data = self._read_logs()
            has_rows = bool(data["runtime_incidents"] or data["event_delivery_attempts"] or data["events"])
            return self._envelope(
                status=ControlCenterStatus.REAL if has_rows else ControlCenterStatus.MISSING,
                source=source,
                truth_state=ControlCenterTruthState.ACTIVE_FRESH if has_rows else ControlCenterTruthState.UNKNOWN,
                data=data,
                last_updated=data.get("latest_at") or data.get("generated_at"),
                warnings=[] if has_rows else ["No runtime incident, DLQ, or event rows are available."],
            )
        except Exception as exc:
            return self._error(source, exc)

    def _service_payload(self, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        payload = loader()
        return self._safe_dict(payload)

    def _payload_status(self, payload: dict[str, Any]) -> ControlCenterStatus:
        raw_status = str(payload.get("status") or payload.get("paper_status") or "").upper()
        if raw_status in {"OK", "HEALTHY", "RUNNING", "RECORDED"}:
            return ControlCenterStatus.REAL
        if raw_status in {"STALE", "DEGRADED", "YELLOW", "RED"}:
            return ControlCenterStatus.STALE if raw_status == "STALE" else ControlCenterStatus.PARTIAL
        if raw_status in {"DATABASE_UNAVAILABLE", "MISSING_TABLES", "MISSING_TRUTH_TABLES", "NO_DATA", "EMPTY", "INSUFFICIENT_DATA"}:
            return ControlCenterStatus.MISSING
        if raw_status == "ERROR":
            return ControlCenterStatus.ERROR
        return ControlCenterStatus.PARTIAL

    def _combined_status(self, statuses: list[ControlCenterStatus]) -> ControlCenterStatus:
        if any(status == ControlCenterStatus.ERROR for status in statuses):
            return ControlCenterStatus.ERROR
        if any(status == ControlCenterStatus.REAL for status in statuses):
            return ControlCenterStatus.PARTIAL if any(status != ControlCenterStatus.REAL for status in statuses) else ControlCenterStatus.REAL
        if any(status == ControlCenterStatus.PARTIAL for status in statuses):
            return ControlCenterStatus.PARTIAL
        if any(status == ControlCenterStatus.STALE for status in statuses):
            return ControlCenterStatus.STALE
        return ControlCenterStatus.MISSING

    def _truth_state_for_status(self, status: ControlCenterStatus) -> ControlCenterTruthState:
        if status == ControlCenterStatus.REAL:
            return ControlCenterTruthState.ACTIVE_FRESH
        if status == ControlCenterStatus.STALE:
            return ControlCenterTruthState.LAST_KNOWN
        if status == ControlCenterStatus.PARTIAL:
            return ControlCenterTruthState.REFRESH_REQUIRED
        return ControlCenterTruthState.UNKNOWN

    def _warnings_for_payload(self, payload: dict[str, Any], fallback: str) -> list[str]:
        warnings = [str(item) for item in payload.get("warnings") or []]
        status = self._payload_status(payload)
        if status in {ControlCenterStatus.MISSING, ControlCenterStatus.PARTIAL, ControlCenterStatus.STALE}:
            warnings.append(fallback)
        return warnings

    def _missing(self, *, source: str | None, warnings: list[str]) -> dict[str, Any]:
        return self._envelope(
            status=ControlCenterStatus.MISSING,
            source=source,
            truth_state=ControlCenterTruthState.UNKNOWN,
            data={},
            warnings=warnings,
        )

    def _error(self, source: str, exc: Exception) -> dict[str, Any]:
        return self._envelope(
            status=ControlCenterStatus.ERROR,
            source=source,
            truth_state=ControlCenterTruthState.UNKNOWN,
            data={},
            errors=[f"{type(exc).__name__}: {exc}"],
        )

    def _envelope(
        self,
        *,
        status: ControlCenterStatus,
        source: str | None,
        truth_state: ControlCenterTruthState,
        data: dict[str, Any] | None = None,
        last_updated: Any = None,
        freshness_state: ControlCenterFreshnessState | None = None,
        runtime_state: ControlCenterRuntimeState | None = None,
        readiness_state: ControlCenterReadinessState | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        last_updated = last_updated or datetime.now(UTC)
        classified_freshness, age = classify_freshness(
            last_updated,
            stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
        )
        if classified_freshness == ControlCenterFreshnessState.STALE and status == ControlCenterStatus.REAL:
            status = ControlCenterStatus.STALE
            truth_state = truth_from_freshness(classified_freshness, has_history=True)
        elif classified_freshness == ControlCenterFreshnessState.MISSING and status == ControlCenterStatus.REAL:
            status = ControlCenterStatus.PARTIAL
            truth_state = ControlCenterTruthState.REFRESH_REQUIRED
        return truth_envelope(
            status=status,
            source=source,
            truth_state=truth_state,
            data=self._json_safe(data or {}),
            last_updated=last_updated,
            stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
            age_seconds=age,
            freshness_state=freshness_state or classified_freshness,
            runtime_state=runtime_state,
            readiness_state=readiness_state,
            warnings=warnings or [],
            errors=errors or [],
        ).to_dict()

    def _read_service_health(self, *, limit: int) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            if not self._table_exists(conn, "service_health"):
                return {"generated_at": generated_at, "services": [], "count": 0, "latest_heartbeat_at": None}
            rows = conn.execute(
                """
                SELECT *
                FROM service_health
                ORDER BY last_heartbeat_at DESC NULLS LAST, updated_at DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        services = [classify_service_runtime(dict(row)) for row in rows]
        stale_services = [row for row in services if row.get("runtime_state") == ControlCenterRuntimeState.STALE.value]
        registered_only = [row for row in services if row.get("runtime_state") == ControlCenterRuntimeState.REGISTERED.value]
        return {
            "generated_at": generated_at,
            "services": self._json_safe(services),
            "count": len(services),
            "running_services_count": sum(1 for row in services if row.get("runtime_state") == ControlCenterRuntimeState.RUNNING.value),
            "registered_only_services": self._json_safe(registered_only),
            "registered_only_services_count": len(registered_only),
            "stale_services": self._json_safe(stale_services),
            "stale_services_count": len(stale_services),
            "latest_heartbeat_at": self._latest_timestamp(services, ("last_heartbeat_at", "updated_at")),
            "read_only": True,
        }

    def _read_overview(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        tables = (
            "system_state",
            "service_health",
            "event_log",
            "risk_evidence_mesh_evaluations",
            "lifecycle_governance_decisions",
            "truth_state_registry",
            "paper_positions",
            "paper_daily_pnl",
            "no_trade_log",
        )
        source_counts: dict[str, int] = {}
        latest_rows: dict[str, Any] = {}
        latest_candidates: list[dict[str, Any]] = []
        with self._factory.connect() as conn:
            for table in tables:
                if not self._table_exists(conn, table):
                    continue
                source_counts[table] = int(
                    conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] or 0
                )
            for table, order_column in (
                ("system_state", "updated_at"),
                ("service_health", "updated_at"),
                ("event_log", "stored_at"),
                ("truth_state_registry", "updated_at"),
            ):
                if self._table_exists(conn, table):
                    row = conn.execute(
                        f"SELECT * FROM {table} ORDER BY {order_column} DESC NULLS LAST, id DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        latest_rows[table] = dict(row)
                        latest_candidates.append(dict(row))
        return {
            "generated_at": generated_at,
            "source_counts": source_counts,
            "latest_rows": self._json_safe(latest_rows),
            "latest_at": self._latest_timestamp(latest_candidates, ("updated_at", "stored_at")),
        }

    def _read_logs(self) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            incidents = self._select_recent(conn, "runtime_incidents", "last_seen_at", 25)
            attempts = self._select_recent(conn, "event_delivery_attempts", "finished_at", 25)
            events = self._select_recent(conn, "event_log", "stored_at", 25)
        all_rows = [*incidents, *attempts, *events]
        return {
            "generated_at": generated_at,
            "runtime_incidents": self._json_safe(incidents),
            "event_delivery_attempts": self._json_safe(attempts),
            "events": self._json_safe(events),
            "latest_at": self._latest_timestamp(all_rows, ("last_seen_at", "finished_at", "stored_at", "occurred_at")),
            "read_only": True,
        }

    def _read_brain_dialogue(self, *, limit: int) -> dict[str, Any]:
        generated_at = datetime.now(UTC).isoformat()
        with self._factory.connect() as conn:
            if not self._table_exists(conn, "brain_dialogue_events"):
                return {"generated_at": generated_at, "events": [], "count": 0, "latest_event_at": None}
            rows = conn.execute(
                """
                SELECT *
                FROM brain_dialogue_events
                ORDER BY timestamp DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return {
            "generated_at": generated_at,
            "events": self._json_safe(rows),
            "count": len(rows),
            "latest_event_at": self._latest_timestamp(list(rows), ("timestamp", "created_at")),
            "read_only": True,
        }

    def _select_recent(self, conn: Any, table: str, order_column: str, limit: int) -> list[dict[str, Any]]:
        if not self._table_exists(conn, table):
            return []
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM {table}
                ORDER BY {order_column} DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        )

    def _table_exists(self, conn: Any, table: str) -> bool:
        row = conn.execute(
            "SELECT to_regclass(%s) AS table_name",
            (table,),
        ).fetchone()
        return bool(row and row.get("table_name"))

    def _timestamp_from_payload(self, payload: dict[str, Any]) -> Any:
        for key in ("last_updated", "updated_at", "generated_at", "latest_at"):
            if payload.get(key):
                return payload[key]
        data = payload.get("data")
        if isinstance(data, dict):
            return self._timestamp_from_payload(data)
        return datetime.now(UTC)

    def _latest_timestamp(self, rows: list[Any], keys: tuple[str, ...]) -> Any:
        latest: Any = None
        for row in rows:
            if not isinstance(row, dict):
                row = dict(row)
            for key in keys:
                value = row.get(key)
                if value is not None and (latest is None or str(value) > str(latest)):
                    latest = value
        return latest

    def _truth_state_from_candidate(self, candidate: dict[str, Any]) -> str:
        raw = str(candidate.get("truth_state") or candidate.get("freshness_status") or "").upper()
        if raw in {item.value for item in ControlCenterTruthState}:
            return raw
        if candidate.get("critical_evidence_missing") or candidate.get("critical_missing_counts"):
            return ControlCenterTruthState.REFRESH_REQUIRED.value
        return ControlCenterTruthState.UNKNOWN.value

    def _safe_dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        return value
