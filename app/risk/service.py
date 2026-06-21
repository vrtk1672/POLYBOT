from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.cooldown_event_repository import CooldownEventRepository
from app.repositories.risk_breach_repository import RiskBreachRepository
from app.repositories.risk_gate_decision_repository import RiskGateDecisionRepository
from app.repositories.risk_gate_run_repository import RiskGateRunRepository
from app.repositories.risk_governor_event_repository import RiskGovernorEventRepository
from app.repositories.risk_governor_state_repository import RiskGovernorStateRepository
from app.repositories.risk_limit_repository import RiskLimitRepository
from app.risk.cooldown_manager import CooldownManager
from app.risk.contracts import RiskGateInput, RiskGovernorState
from app.risk.contracts import RiskBreach
from app.risk.manual_override_auditor import ManualOverrideAuditor
from app.risk.risk_breach_detector import RiskBreachDetector
from app.risk.risk_errors import RiskEvaluationBlocked
from app.risk.risk_gate import RiskGate
from app.risk.risk_governor import RiskGovernor
from app.risk.risk_limit_manager import RiskLimitManager
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class RiskService:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._state_governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.gate = RiskGate()
        self.governor = RiskGovernor()
        self.limit_manager = RiskLimitManager()
        self.breach_detector = RiskBreachDetector()
        self.cooldown_manager = CooldownManager()
        self.override_auditor = ManualOverrideAuditor()
        self.gate_runs = RiskGateRunRepository()
        self.gate_decisions = RiskGateDecisionRepository()
        self.governor_states = RiskGovernorStateRepository()
        self.governor_events = RiskGovernorEventRepository()
        self.limits = RiskLimitRepository()
        self.breaches = RiskBreachRepository()
        self.cooldowns = CooldownEventRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                if not _exists(conn, "risk_gate_decisions"):
                    return _empty("EMPTY")
                gate = self.gate_runs.health(conn)
                latest = self.governor_states.latest(conn) or {}
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND decision='APPROVED') AS approved_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND blocked IS TRUE) AS blocked_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND decision='INSUFFICIENT_DATA') AS insufficient_data_count
                    FROM risk_gate_decisions
                    """
                ).fetchone()
                breaches = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS breaches_today FROM risk_breaches").fetchone()
                cooldowns = conn.execute("SELECT COUNT(*) AS count FROM cooldown_events WHERE active IS TRUE AND (expires_at IS NULL OR expires_at > now())").fetchone()
            return {
                "status": "HEALTHY" if latest else "EMPTY",
                "governor_status": latest.get("governor_status"),
                "gate_runs_today": int((gate or {}).get("gate_runs_today") or 0),
                "approved_today": int((stats or {}).get("approved_today") or 0),
                "blocked_today": int((stats or {}).get("blocked_today") or 0),
                "breaches_today": int((breaches or {}).get("breaches_today") or 0),
                "cooldowns_active": int((cooldowns or {}).get("count") or 0),
                "latest_gate_ts": _iso((gate or {}).get("latest_gate_ts")),
                "latest_governor_update_ts": _iso(latest.get("updated_at")),
                "errors_today": int((gate or {}).get("errors_today") or 0),
                "insufficient_data_count": int((stats or {}).get("insufficient_data_count") or 0),
            }
        except Exception as exc:
            data = _empty("ERROR")
            data["error"] = str(exc)
            data["errors_today"] = 1
            return data

    def rebuild_governor(self, *, dry_run: bool = False, manual_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        payload = manual_payload or {}
        state = self.governor.rebuild(runtime_mode=self._runtime_mode(), payload=payload)
        defaults = self.limit_manager.default_limits()
        breaches = self.breach_detector.detect_governor_breaches(state)
        seen = {breach.breach_type + str(breach.engine) for breach in breaches}
        for item in state.active_breaches:
            breach = RiskBreach(**item)
            key = breach.breach_type + str(breach.engine)
            if key not in seen:
                breaches.append(breach)
                seen.add(key)
        cooldowns = []
        for breach in breaches:
            if breach.breach_type in {"MAX_ENGINE_LOSS", "MAX_DAILY_LOSS"}:
                breach.cooldown_created = True
                cooldowns.append(self.cooldown_manager.from_breach(breach))
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "governor_state": state.model_dump(mode="json"), "breaches": [b.model_dump(mode="json") for b in breaches]}
        with self._factory.connect() as conn:
            with conn.transaction():
                self.limits.seed_defaults(conn, defaults)
                row = self.governor_states.insert(conn, state)
                breach_rows = self.breaches.insert_many(conn, breaches)
                cooldown_rows = self.cooldowns.insert_many(conn, cooldowns)
                self.governor_events.insert(
                    conn,
                    event_id=f"risk_event_{uuid4().hex}",
                    event_type="risk.governor.state.updated",
                    new_status=state.governor_status,
                    actor="risk_service",
                    reason="risk governor rebuilt from DB/runtime truth or explicit smoke input",
                    details=state.model_dump(mode="json"),
                    correlation_id=state.state_id,
                )
            conn.commit()
        self._publish(EventType.RISK_GOVERNOR_STATE_UPDATED.value, {"state_id": state.state_id, "governor_status": state.governor_status})
        for breach in breaches:
            self._publish(EventType.RISK_BREACH_DETECTED.value, {"breach_id": breach.breach_id, "breach_type": breach.breach_type, "blocked": breach.blocked})
        return {"dry_run": False, "written": True, "governor_state": _serialize(row), "breaches": [_serialize(row) for row in breach_rows], "cooldowns": [_serialize(row) for row in cooldown_rows]}

    def evaluate_gate(self, *, market_id: str, strategy_route_id: int | None = None, allocation_id: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        run_id = f"risk_gate_{uuid4().hex}"
        if not self._factory.enabled and manual_input:
            payload = self._input_from_manual(market_id, manual_input)
            decision = self.gate.evaluate(payload, run_id=run_id)
            return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json")}
        with self._factory.connect() as conn:
            payload = self._input_from_manual(market_id, manual_input) if manual_input else self._input_from_db(conn, market_id, strategy_route_id=strategy_route_id, allocation_id=allocation_id)
            decision = self.gate.evaluate(payload, run_id=run_id)
            if dry_run:
                return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json")}
            with conn.transaction():
                self.gate_runs.insert_started(
                    conn,
                    run_id=run_id,
                    market_id=payload.market_id,
                    market_family=payload.market_family,
                    side=payload.side,
                    engine=payload.engine,
                    strategy_route_id=(payload.strategy_route or {}).get("id"),
                    allocation_id=(payload.capital_allocation or {}).get("allocation_id"),
                    runtime_mode=self._runtime_mode(),
                    input_sources=self._input_sources(payload),
                    input_completeness_score=payload.data_completeness_score,
                )
                row = self.gate_decisions.insert(conn, decision)
                self.gate_runs.finish(conn, run_id)
            conn.commit()
        event = EventType.RISK_GATE_APPROVED if decision.approved else EventType.RISK_GATE_BLOCKED
        if decision.decision == "REDUCED":
            event = EventType.RISK_GATE_REDUCED
        if decision.decision == "INSUFFICIENT_DATA":
            event = EventType.RISK_GATE_INSUFFICIENT_DATA
        self._publish(event.value, {"run_id": run_id, "market_id": market_id, "decision": decision.decision, "approved": decision.approved})
        return {"dry_run": False, "written": True, "decision": _serialize(row)}

    def create_override(self, *, payload: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
        self._assert_allowed()
        governor_status = payload.get("governor_status")
        if self._factory.enabled:
            with self._factory.connect() as conn:
                latest = self.governor_states.latest(conn) or {}
                governor_status = governor_status or latest.get("governor_status")
        override = self.override_auditor.validate(payload, governor_status=governor_status)
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "override": override}
        with self._factory.connect() as conn:
            with conn.transaction():
                row = self.governor_events.insert(
                    conn,
                    event_id=override["override_id"],
                    event_type="risk.manual_override.created",
                    actor=override["actor"],
                    reason=override["reason"],
                    details=override,
                    correlation_id=override["override_id"],
                )
            conn.commit()
        self._publish(EventType.RISK_MANUAL_OVERRIDE_CREATED.value, {"override_id": override["override_id"], "scope": override["scope"]})
        return {"dry_run": False, "written": True, "override": _serialize(row)}

    def governor_latest(self) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.governor_states.latest(conn)) or {"governor_state": None}

    def limits_list(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            if not self.limits.list(conn):
                self.limits.seed_defaults(conn, self.limit_manager.default_limits())
                conn.commit()
            return [_serialize(row) for row in self.limits.list(conn)]

    def breaches_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.breaches.recent(conn, limit)]

    def cooldowns_active(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.cooldowns.active(conn)]

    def gate_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.gate_decisions.recent(conn, limit)]

    def gate_detail(self, run_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return {"run_id": run_id, "decision": _serialize(self.gate_decisions.by_run(conn, run_id))}

    def _input_from_manual(self, market_id: str, manual: dict[str, Any]) -> RiskGateInput:
        governor = manual.get("governor_state") or {"governor_status": "OK", "data_confidence": 0.85}
        return RiskGateInput(
            market_id=market_id,
            market_family=manual.get("market_family"),
            side=manual.get("side") or "UNKNOWN",
            engine=manual.get("engine") or (manual.get("strategy_route") or {}).get("selected_engine") or "NO_TRADE",
            strategy_route=manual.get("strategy_route") or {},
            capital_allocation=manual.get("capital_allocation"),
            opportunity_score=manual.get("opportunity_score") or {},
            technical_truth=manual.get("technical_truth") or {},
            rules_risk=manual.get("rules_risk") or {},
            market_memory=manual.get("market_memory") or {},
            governor_state=governor,
            risk_limits=manual.get("risk_limits") or {},
            exit_plan_candidate=manual.get("exit_plan_candidate") or {},
            data_completeness_score=manual.get("data_completeness_score", 0.85),
            manual_override=manual.get("manual_override"),
        )

    def _input_from_db(self, conn: Connection, market_id: str, *, strategy_route_id: int | None, allocation_id: str | None) -> RiskGateInput:
        route = _latest_route(conn, market_id, strategy_route_id) or {}
        allocation = _latest_allocation(conn, market_id, allocation_id)
        governor = self.governor_states.latest(conn)
        if not governor:
            governor_state = self.governor.rebuild(runtime_mode=self._runtime_mode(), payload={"insufficient_data": True, "insufficient_data_reasons": ["missing_governor_state"]})
        else:
            governor_state = _governor_from_row(governor)
        return RiskGateInput(
            market_id=market_id,
            market_family=route.get("market_family") or (allocation or {}).get("market_family"),
            side=route.get("side") or (allocation or {}).get("side") or "UNKNOWN",
            engine=route.get("selected_engine") or (allocation or {}).get("engine") or "NO_TRADE",
            strategy_route=route,
            capital_allocation=allocation,
            opportunity_score=_latest(conn, "opportunity_scores_v2", market_id) or {},
            technical_truth={
                "liquidity_signal": _latest(conn, "liquidity_signals", market_id, order_by="ts") or {},
                "orderbook_signal": _latest(conn, "orderbook_signals", market_id, order_by="ts") or {},
            },
            rules_risk=_latest(conn, "rules_analysis", market_id) or {},
            market_memory=_latest(conn, "market_memory_v2", market_id, order_by="updated_at") or {},
            governor_state=governor_state,
            data_completeness_score=float(route.get("route_confidence") or 0.0),
        )

    def _assert_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._state_governor.assert_can_execute(RuntimeAction.SCORE_MARKET)
        except Exception as exc:
            raise RiskEvaluationBlocked("risk evaluation blocked by runtime mode") from exc

    def _runtime_mode(self) -> str | None:
        try:
            return self._state_governor.get_current_state().current_mode.value
        except Exception:
            return None

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type, payload, "risk", aggregate_type="risk", aggregate_id=payload.get("market_id") or payload.get("state_id") or "risk")

    @staticmethod
    def _input_sources(payload: RiskGateInput) -> list[str]:
        sources = []
        if payload.strategy_route:
            sources.append("strategy_route")
        if payload.capital_allocation:
            sources.append("capital_allocation")
        if payload.governor_state:
            sources.append("risk_governor")
        return sources


def _exists(conn: Connection, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _latest(conn: Connection, table: str, market_id: str, *, order_by: str = "created_at") -> dict[str, Any] | None:
    if not _exists(conn, table):
        return None
    rows = conn.execute(f"SELECT * FROM {table} WHERE market_id=%s ORDER BY {order_by} DESC, id DESC LIMIT 1", (market_id,)).fetchall()
    return dict(rows[0]) if rows else None


def _latest_route(conn: Connection, market_id: str, strategy_route_id: int | None) -> dict[str, Any] | None:
    if not _exists(conn, "strategy_routes_v2"):
        return None
    if strategy_route_id is not None:
        row = conn.execute("SELECT * FROM strategy_routes_v2 WHERE id=%s LIMIT 1", (strategy_route_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM strategy_routes_v2 WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()
    return dict(row) if row else None


def _latest_allocation(conn: Connection, market_id: str, allocation_id: str | None) -> dict[str, Any] | None:
    if not _exists(conn, "capital_allocations_v2"):
        return None
    if allocation_id:
        row = conn.execute("SELECT * FROM capital_allocations_v2 WHERE allocation_id=%s LIMIT 1", (allocation_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM capital_allocations_v2 WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()
    return dict(row) if row else None


def _governor_from_row(row: dict[str, Any]) -> RiskGovernorState:
    return RiskGovernorState(
        state_id=row["state_id"],
        runtime_mode=row.get("runtime_mode"),
        governor_status=row.get("governor_status") or "OK",
        kill_switch_active=row.get("kill_switch_active") or False,
        attack_mode_allowed=row.get("attack_mode_allowed") or False,
        cooldown_active=row.get("cooldown_active") or False,
        daily_loss_usd=row.get("daily_loss_usd") or 0,
        weekly_loss_usd=row.get("weekly_loss_usd") or 0,
        open_positions_count=row.get("open_positions_count") or 0,
        open_exposure_usd=row.get("open_exposure_usd") or 0,
        max_daily_loss_usd=row.get("max_daily_loss_usd") or 50,
        max_weekly_loss_usd=row.get("max_weekly_loss_usd") or 150,
        max_open_positions=row.get("max_open_positions") or 5,
        max_total_exposure_usd=row.get("max_total_exposure_usd") or 500,
        max_engine_loss=row.get("max_engine_loss_json") or {},
        max_market_family_exposure=row.get("max_market_family_exposure_json") or {},
        active_cooldowns=row.get("active_cooldowns_json") or [],
        active_breaches=row.get("active_breaches_json") or [],
        manual_overrides=row.get("manual_overrides_json") or [],
        data_confidence=row.get("data_confidence") or 0,
        insufficient_data=row.get("insufficient_data") or False,
        insufficient_data_reasons=row.get("insufficient_data_reasons_json") or [],
    )


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "governor_status": None, "gate_runs_today": 0, "approved_today": 0, "blocked_today": 0, "breaches_today": 0, "cooldowns_active": 0, "latest_gate_ts": None, "latest_governor_update_ts": None, "errors_today": 0}


def _iso(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
