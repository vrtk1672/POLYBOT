from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from psycopg import Connection

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.exit_cortex.contracts import ExitPlan
from app.exit_cortex.exit_event_manager import ExitEventManager
from app.exit_cortex.exit_failure_handler import ExitFailureHandler
from app.exit_cortex.exit_intent_builder import ExitIntentBuilder
from app.exit_cortex.exit_plan_builder import ExitPlanBuilder
from app.exit_cortex.exit_quality import ExitQualityScorer
from app.exit_cortex.exit_trigger_evaluator import ExitTriggerEvaluator
from app.exit_cortex.liquidity_exit_checker import LiquidityExitChecker
from app.exit_cortex.position_monitor import PositionMonitor
from app.repositories.exit_event_repository import ExitEventRepository
from app.repositories.exit_failure_repository import ExitFailureRepository
from app.repositories.exit_intent_repository import ExitIntentRepository
from app.repositories.exit_plan_repository import ExitPlanRepository
from app.repositories.exit_quality_repository import ExitQualityRepository
from app.runtime.state_governor import StateGovernor


class ExitCortexService:
    live_certified = False

    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._state_governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.plan_builder = ExitPlanBuilder()
        self.trigger_evaluator = ExitTriggerEvaluator()
        self.intent_builder = ExitIntentBuilder()
        self.quality_scorer = ExitQualityScorer()
        self.failure_handler = ExitFailureHandler()
        self.event_manager = ExitEventManager()
        self.liquidity_checker = LiquidityExitChecker()
        self.position_monitor = PositionMonitor()
        self.plans = ExitPlanRepository()
        self.intents = ExitIntentRepository()
        self.events = ExitEventRepository()
        self.qualities = ExitQualityRepository()
        self.failures = ExitFailureRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                if not _exists(conn, "exit_plans"):
                    return _empty("EMPTY")
                plans = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE plan_status IN ('ACTIVE','PENDING_ORDER')) AS active_exit_plans,
                      COUNT(*) FILTER (WHERE insufficient_data IS TRUE) AS insufficient_data_count
                    FROM exit_plans
                    """
                ).fetchone()
                intents = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS intents_today FROM exit_intents").fetchone()
                events = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND event_type LIKE '%TRIGGERED%') AS triggers_today FROM exit_events").fetchone()
                failures = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS failures_today FROM exit_failures").fetchone()
                quality = conn.execute("SELECT AVG(exit_quality_score) AS avg_exit_quality FROM exit_quality WHERE created_at::date=CURRENT_DATE").fetchone()
                orphans = self.position_monitor.orphan_orders(conn, limit=1000) if _exists(conn, "orders_v2") else []
            return {
                "status": "HEALTHY",
                "active_exit_plans": int((plans or {}).get("active_exit_plans") or 0),
                "intents_today": int((intents or {}).get("intents_today") or 0),
                "triggers_today": int((events or {}).get("triggers_today") or 0),
                "failures_today": int((failures or {}).get("failures_today") or 0),
                "orphan_orders_count": len(orphans),
                "avg_exit_quality": _number((quality or {}).get("avg_exit_quality")),
                "live_certified": False,
                "errors_today": int((failures or {}).get("failures_today") or 0),
                "insufficient_data_count": int((plans or {}).get("insufficient_data_count") or 0),
            }
        except Exception as exc:
            return {**_empty("ERROR"), "error": str(exc)}

    def create_plan(
        self,
        *,
        market_id: str,
        order_id: str | None = None,
        strategy_route_id: int | None = None,
        allocation_id: str | None = None,
        risk_decision_id: int | None = None,
        execution_order_id: str | None = None,
        dry_run: bool = False,
        manual_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._load_plan_input(
            market_id,
            order_id=execution_order_id or order_id,
            strategy_route_id=strategy_route_id,
            allocation_id=allocation_id,
            risk_decision_id=risk_decision_id,
            manual_input=manual_input,
        )
        plan = self.plan_builder.build(market_id=market_id, order=payload.get("order"), strategy_route=payload.get("strategy_route"), risk_decision=payload.get("risk_decision"), manual=manual_input or {})
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "plan": plan.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                row = self.plans.insert(conn, plan)
                event_type = "EXIT_PLAN_BLOCKED" if plan.insufficient_data else "EXIT_PLAN_CREATED"
                self.events.insert(
                    conn,
                    event_type=event_type,
                    exit_plan_id=plan.exit_plan_id,
                    order_id=plan.order_id,
                    market_id=plan.market_id,
                    new_status=plan.plan_status,
                    reason="exit plan has insufficient data" if plan.insufficient_data else "exit plan created",
                    details={"insufficient_data_reasons": plan.insufficient_data_reasons},
                )
            conn.commit()
        self._publish(EventType.EXIT_PLAN_BLOCKED.value if plan.insufficient_data else EventType.EXIT_PLAN_CREATED.value, {"exit_plan_id": plan.exit_plan_id, "market_id": market_id, "plan_status": plan.plan_status})
        return {"dry_run": False, "written": True, "plan": _serialize(row)}

    def evaluate(self, *, exit_plan_id: str, dry_run: bool = False, current: dict[str, Any] | None = None) -> dict[str, Any]:
        current = current or {}
        with self._factory.connect() as conn:
            row = self.plans.by_exit_plan_id(conn, exit_plan_id)
            if not row:
                raise ValueError(f"exit plan not found: {exit_plan_id}")
        plan = _plan_from_row(row)
        decision = self.trigger_evaluator.evaluate(plan=plan, current=current)
        if not decision.should_exit:
            return {"dry_run": dry_run, "written": False, "decision": decision.model_dump(mode="json")}

        runtime_block = self._runtime_block(plan=plan, current=current, emergency=decision.selected_reason == "EMERGENCY_EXIT")
        liquidity_ok, liquidity_reasons = self.liquidity_checker.check(plan=plan, current=current)
        if runtime_block or not liquidity_ok:
            reasons = ([runtime_block] if runtime_block else []) + liquidity_reasons
            failure = self.failure_handler.failure(plan=plan, failure_type="EXIT_BLOCKED", reason=";".join(reasons), details={"selected_reason": decision.selected_reason, "reasons": reasons})
            if dry_run or not self._factory.enabled:
                decision.blocked_reasons = reasons
                return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json"), "failure": failure.model_dump(mode="json")}
            with self._factory.connect() as conn:
                with conn.transaction():
                    failure_row = self.failures.insert(conn, failure)
                    self.events.insert(conn, event_type="EXIT_FAILED" if liquidity_reasons else "EXIT_INTENT_BLOCKED", exit_plan_id=plan.exit_plan_id, order_id=plan.order_id, market_id=plan.market_id, reason=failure.reason, details=failure.details)
                conn.commit()
            self._publish(EventType.EXIT_FAILURE_RECORDED.value, {"failure_id": failure.failure_id, "exit_plan_id": plan.exit_plan_id, "market_id": plan.market_id, "failure_type": failure.failure_type})
            decision.blocked_reasons = reasons
            return {"dry_run": False, "written": True, "decision": decision.model_dump(mode="json"), "failure": _serialize(failure_row)}

        trigger_snapshot = {"selected_reason": decision.selected_reason, "triggers": [trigger.model_dump(mode="json") for trigger in decision.triggers if trigger.triggered]}
        intent = self.intent_builder.build(plan=plan, reason=decision.selected_reason or "EXIT_TRIGGER", current=current, trigger_snapshot=trigger_snapshot)
        quality = self.quality_scorer.score(plan=plan, intent=intent, current=current)
        decision.exit_intent = intent
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json"), "intent": intent.model_dump(mode="json"), "quality": quality.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                intent_row = self.intents.insert(conn, intent)
                quality_row = self.qualities.insert(conn, quality)
                trigger_event_type = self.event_manager.event_type_for_trigger(decision.selected_reason or "EXIT_TRIGGER")
                self.events.insert(conn, event_type="EXIT_TRIGGER_DETECTED", exit_plan_id=plan.exit_plan_id, order_id=plan.order_id, market_id=plan.market_id, reason=decision.selected_reason or "exit_trigger", details=trigger_snapshot)
                self.events.insert(conn, event_type=trigger_event_type, exit_plan_id=plan.exit_plan_id, exit_intent_id=intent.exit_intent_id, order_id=plan.order_id, market_id=plan.market_id, reason=intent.reason, details=intent.trigger_snapshot)
                self.events.insert(conn, event_type="EXIT_INTENT_CREATED", exit_plan_id=plan.exit_plan_id, exit_intent_id=intent.exit_intent_id, order_id=plan.order_id, market_id=plan.market_id, new_status=intent.intent_status, reason="internal paper/shadow exit intent created", details={"execution_mode": intent.execution_mode})
            conn.commit()
        self._publish(_event_type_for_selected(decision.selected_reason), {"exit_plan_id": plan.exit_plan_id, "exit_intent_id": intent.exit_intent_id, "market_id": plan.market_id})
        self._publish(EventType.EXIT_INTENT_CREATED.value, {"exit_plan_id": plan.exit_plan_id, "exit_intent_id": intent.exit_intent_id, "market_id": plan.market_id, "execution_mode": intent.execution_mode})
        self._publish(EventType.EXIT_QUALITY_RECORDED.value, {"exit_plan_id": plan.exit_plan_id, "quality_score": quality.exit_quality_score, "market_id": plan.market_id})
        return {"dry_run": False, "written": True, "decision": decision.model_dump(mode="json"), "intent": _serialize(intent_row), "quality": _serialize(quality_row)}

    def emergency(self, *, exit_plan_id: str | None = None, order_id: str | None = None, reason: str, dry_run: bool = False, current: dict[str, Any] | None = None) -> dict[str, Any]:
        current = {**(current or {}), "emergency": True, "emergency_reason": reason}
        plan_id = exit_plan_id
        with self._factory.connect() as conn:
            row = self.plans.by_exit_plan_id(conn, plan_id) if plan_id else self.plans.latest_for_order(conn, order_id or "")
            if not row:
                raise ValueError("exit plan required for emergency exit intent")
            plan_id = row["exit_plan_id"]
        return self.evaluate(exit_plan_id=str(plan_id), dry_run=dry_run, current=current)

    def recent_plans(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.plans.recent(conn, limit=limit)]

    def plan_detail(self, exit_plan_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            row = self.plans.by_exit_plan_id(conn, exit_plan_id)
            if not row:
                raise ValueError(f"exit plan not found: {exit_plan_id}")
            return {
                "plan": _serialize(row),
                "intents": [_serialize(item) for item in self.intents.by_plan(conn, exit_plan_id)],
                "events": [_serialize(item) for item in self.events.by_plan(conn, exit_plan_id)],
                "quality": [_serialize(item) for item in self.qualities.by_plan(conn, exit_plan_id)],
                "failures": [_serialize(item) for item in self.failures.by_plan(conn, exit_plan_id)],
            }

    def recent_intents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.intents.recent(conn, limit=limit)]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.events.recent(conn, limit=limit)]

    def recent_failures(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.failures.recent(conn, limit=limit)]

    def recent_quality(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.qualities.recent(conn, limit=limit)]

    def orphan_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.position_monitor.orphan_orders(conn, limit=limit)]

    def _load_plan_input(
        self,
        market_id: str,
        *,
        order_id: str | None,
        strategy_route_id: int | None,
        allocation_id: str | None,
        risk_decision_id: int | None,
        manual_input: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(manual_input or {})
        if not self._factory.enabled:
            return payload
        with self._factory.connect() as conn:
            if order_id and _exists(conn, "orders_v2"):
                payload.setdefault("order", conn.execute("SELECT * FROM orders_v2 WHERE order_id=%s LIMIT 1", (order_id,)).fetchone() or {})
            if strategy_route_id and _exists(conn, "strategy_routes_v2"):
                payload.setdefault("strategy_route", conn.execute("SELECT * FROM strategy_routes_v2 WHERE id=%s LIMIT 1", (strategy_route_id,)).fetchone() or {})
            if allocation_id and _exists(conn, "capital_allocations_v2"):
                payload.setdefault("allocation", conn.execute("SELECT * FROM capital_allocations_v2 WHERE allocation_id=%s LIMIT 1", (allocation_id,)).fetchone() or {})
            if risk_decision_id and _exists(conn, "risk_gate_decisions"):
                payload.setdefault("risk_decision", conn.execute("SELECT * FROM risk_gate_decisions WHERE id=%s LIMIT 1", (risk_decision_id,)).fetchone() or {})
        payload.setdefault("market_id", market_id)
        return payload

    def _runtime_block(self, *, plan: ExitPlan, current: dict[str, Any], emergency: bool) -> str | None:
        mode = str(current.get("runtime_mode") or self._runtime_mode()).upper()
        if mode == "DATA_ONLY":
            return "DATA_ONLY_evaluation_only"
        if mode == "PAPER" and plan.exit_mode != "PAPER_SIM_EXIT":
            return "PAPER_allows_paper_sim_exit_only"
        if mode == "SHADOW_LIVE" and plan.exit_mode != "SHADOW_EXIT_PLAN":
            return "SHADOW_LIVE_allows_shadow_exit_plan_only"
        if mode in {"SMALL_LIVE", "ATTACK_MODE"}:
            return "LIVE_NOT_CERTIFIED"
        if mode == "KILL" and not emergency:
            return "KILL_blocks_non_emergency_exit_intent"
        return None

    def _runtime_mode(self) -> str:
        try:
            state = self._state_governor.get_current_state()
            return str(getattr(state.current_mode, "value", state.current_mode))
        except Exception:
            return "DATA_ONLY"

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._event_bus.publish(event_type, payload, "exit_cortex_v2", aggregate_type="exit_cortex", aggregate_id=str(payload.get("exit_plan_id") or payload.get("market_id") or "exit"))
        except Exception:
            return


def _empty(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "active_exit_plans": 0,
        "intents_today": 0,
        "triggers_today": 0,
        "failures_today": 0,
        "orphan_orders_count": 0,
        "avg_exit_quality": None,
        "live_certified": False,
        "errors_today": 0,
    }


def _exists(conn: Connection, table: str) -> bool:
    return bool(conn.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (table,)).fetchone()["exists"])


def _serialize(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, list):
        return [_serialize(item) for item in row]
    if isinstance(row, dict):
        return {key: _serialize(value) for key, value in row.items()}
    if isinstance(row, Decimal):
        return float(row)
    if isinstance(row, datetime):
        return row.isoformat()
    return row


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _plan_from_row(row: dict[str, Any]) -> ExitPlan:
    return ExitPlan(
        exit_plan_id=row["exit_plan_id"],
        market_id=row["market_id"],
        market_family=row.get("market_family"),
        side=row.get("side") or "YES",
        engine=row.get("engine") or "SAFE",
        strategy_route_id=row.get("strategy_route_id"),
        allocation_id=row.get("allocation_id"),
        risk_gate_run_id=row.get("risk_gate_run_id"),
        order_id=row.get("order_id"),
        position_ref=row.get("position_ref"),
        entry_price=float(row.get("entry_price") or 0),
        entry_size=float(row.get("entry_size") or 0),
        target_exit=None if row.get("target_exit") is None else float(row.get("target_exit")),
        partial_take_profit=None if row.get("partial_take_profit") is None else float(row.get("partial_take_profit")),
        partial_take_profit_pct=None if row.get("partial_take_profit_pct") is None else float(row.get("partial_take_profit_pct")),
        stop_loss=None if row.get("stop_loss") is None else float(row.get("stop_loss")),
        max_hold_seconds=row.get("max_hold_seconds"),
        invalidation_rule=row.get("invalidation_rule_json") or {},
        liquidity_exit_check=row.get("liquidity_exit_check_json") or {},
        emergency_exit=row.get("emergency_exit_json") or {},
        momentum_decay_exit=row.get("momentum_decay_exit_json") or {},
        spread_exit=row.get("spread_exit_json") or {},
        news_invalidated_exit=row.get("news_invalidated_exit_json") or {},
        exit_mode=row.get("exit_mode") or "PAPER_SIM_EXIT",
        plan_status=row.get("plan_status") or "ACTIVE",
        created_from=row.get("created_from") or "exit_cortex_v2",
        data_confidence=float(row.get("data_confidence") or 0),
        insufficient_data=bool(row.get("insufficient_data")),
        insufficient_data_reasons=row.get("insufficient_data_reasons_json") or [],
    )


def _event_type_for_selected(selected: str | None) -> str:
    mapping = {
        "TAKE_PROFIT": EventType.EXIT_TAKE_PROFIT_TRIGGERED.value,
        "PARTIAL_TAKE_PROFIT": EventType.EXIT_PARTIAL_TAKE_PROFIT_TRIGGERED.value,
        "STOP_LOSS": EventType.EXIT_STOP_LOSS_TRIGGERED.value,
        "MAX_HOLD": EventType.EXIT_MAX_HOLD_TRIGGERED.value,
        "NEWS_INVALIDATED": EventType.EXIT_NEWS_INVALIDATED_TRIGGERED.value,
        "SPREAD_EXIT": EventType.EXIT_SPREAD_EXIT_TRIGGERED.value,
        "MOMENTUM_DECAY": EventType.EXIT_MOMENTUM_DECAY_TRIGGERED.value,
        "EMERGENCY_EXIT": EventType.EXIT_EMERGENCY_TRIGGERED.value,
    }
    return mapping.get(selected or "", EventType.EXIT_TRIGGER_DETECTED.value)
