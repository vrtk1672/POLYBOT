from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.execution_v2.cancel_condition_evaluator import CancelConditionEvaluator
from app.execution_v2.contracts import ExecutionPrecheck, OrderContract, expires_at
from app.execution_v2.execution_errors import ExecutionBlocked
from app.execution_v2.order_contract_builder import OrderContractBuilder
from app.execution_v2.order_lifecycle_manager import OrderLifecycleManager
from app.execution_v2.paper_execution_simulator import PaperExecutionSimulator
from app.execution_v2.shadow_execution_planner import ShadowExecutionPlanner
from app.repositories.execution_error_repository import ExecutionErrorRepository
from app.repositories.execution_latency_repository import ExecutionLatencyRepository
from app.repositories.execution_quality_repository import ExecutionQualityRepository
from app.repositories.fill_v2_repository import FillV2Repository
from app.repositories.order_event_v2_repository import OrderEventV2Repository
from app.repositories.order_v2_repository import OrderV2Repository
from app.runtime.state_governor import StateGovernor


class ExecutionV2Service:
    live_certified = False

    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None, state_governor: StateGovernor | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._state_governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.builder = OrderContractBuilder()
        self.paper = PaperExecutionSimulator()
        self.shadow = ShadowExecutionPlanner()
        self.lifecycle = OrderLifecycleManager()
        self.cancel_evaluator = CancelConditionEvaluator()
        self.orders = OrderV2Repository()
        self.order_events = OrderEventV2Repository()
        self.fills = FillV2Repository()
        self.errors = ExecutionErrorRepository()
        self.latency = ExecutionLatencyRepository()
        self.quality = ExecutionQualityRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                if not _exists(conn, "orders_v2"):
                    return _empty("EMPTY")
                stats = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS orders_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND execution_mode='PAPER_SIM') AS paper_orders_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND execution_mode='SHADOW_PLAN') AS shadow_plans_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND order_status='CANCELLED') AS cancelled_today
                    FROM orders_v2
                    """
                ).fetchone()
                fills = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS fills_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND partial IS TRUE) AS partial_fills_today,
                      COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE AND fill_status='FAILED') AS failed_fills_today,
                      AVG(slippage_bps) AS avg_slippage_bps
                    FROM fills_v2
                    """
                ).fetchone()
                quality = conn.execute("SELECT AVG(execution_quality_score) AS avg_quality_score FROM execution_quality WHERE created_at::date=CURRENT_DATE").fetchone()
                errors = conn.execute("SELECT COUNT(*) FILTER (WHERE created_at::date=CURRENT_DATE) AS errors_today FROM execution_errors").fetchone()
            return {
                "status": "HEALTHY",
                "orders_today": int((stats or {}).get("orders_today") or 0),
                "paper_orders_today": int((stats or {}).get("paper_orders_today") or 0),
                "shadow_plans_today": int((stats or {}).get("shadow_plans_today") or 0),
                "fills_today": int((fills or {}).get("fills_today") or 0),
                "partial_fills_today": int((fills or {}).get("partial_fills_today") or 0),
                "failed_fills_today": int((fills or {}).get("failed_fills_today") or 0),
                "cancelled_today": int((stats or {}).get("cancelled_today") or 0),
                "avg_slippage_bps": _float((fills or {}).get("avg_slippage_bps")),
                "avg_quality_score": _float((quality or {}).get("avg_quality_score")),
                "errors_today": int((errors or {}).get("errors_today") or 0),
                "live_certified": False,
            }
        except Exception as exc:
            data = _empty("ERROR")
            data["error"] = str(exc)
            data["errors_today"] = 1
            return data

    def precheck(self, *, market_id: str, execution_mode: str, strategy_route_id: int | None = None, allocation_id: str | None = None, risk_decision_id: int | None = None, exit_plan_id: str | None = None, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._load_input(market_id, strategy_route_id=strategy_route_id, allocation_id=allocation_id, risk_decision_id=risk_decision_id, manual_input=manual_input)
        precheck = self._precheck_payload(payload, execution_mode=execution_mode, exit_plan_id=exit_plan_id)
        return {"allowed": precheck.allowed, "precheck": precheck.model_dump(mode="json")}

    def paper_simulate(self, *, market_id: str, strategy_route_id: int | None = None, allocation_id: str | None = None, risk_decision_id: int | None = None, exit_plan_id: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._load_input(market_id, strategy_route_id=strategy_route_id, allocation_id=allocation_id, risk_decision_id=risk_decision_id, manual_input=manual_input)
        precheck = self._precheck_payload(payload, execution_mode="PAPER_SIM", exit_plan_id=exit_plan_id)
        if not precheck.allowed:
            return self._blocked(market_id, "PAPER_SIM", precheck, dry_run=dry_run)
        contract = self._build_contract(market_id, payload, exit_plan_id=exit_plan_id or "", execution_mode="PAPER_SIM", dry_run=dry_run)
        result, quality = self.paper.simulate(contract)
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "precheck": precheck.model_dump(mode="json"), "order_contract": contract.model_dump(mode="json"), "result": result.model_dump(mode="json"), "quality": quality.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                order_row = self.orders.insert(conn, contract, order_status=result.order_status, expires_at=expires_at(contract.ttl_seconds), filled_size=result.filled_size, remaining_size=result.remaining_size, avg_fill_price=result.avg_fill_price)
                self.order_events.insert(conn, order_id=contract.order_id, event_type="ORDER_CREATED", new_status="CREATED", reason="internal paper execution contract created", details={"execution_mode": "PAPER_SIM"})
                self.order_events.insert(conn, order_id=contract.order_id, event_type="ORDER_SUBMITTED_PAPER", old_status="CREATED", new_status=result.order_status, reason="paper simulation completed", details=result.model_dump(mode="json"))
                fill_rows = [self.fills.insert(conn, fill) for fill in result.fills]
                quality_row = self.quality.insert(conn, quality)
                self.latency.insert(conn, latency_id=f"execution_latency_{uuid4().hex}", order_id=contract.order_id, market_id=market_id, stage="paper_simulate", latency_ms=0.0, started_at=datetime.now(UTC), finished_at=datetime.now(UTC))
            conn.commit()
        self._publish(EventType.EXECUTION_ORDER_SUBMITTED_PAPER.value, {"order_id": contract.order_id, "market_id": market_id, "order_status": result.order_status})
        for fill in result.fills:
            self._publish(EventType.EXECUTION_FILL_CREATED.value, {"fill_id": fill.fill_id, "order_id": contract.order_id, "market_id": market_id, "fill_status": fill.fill_status})
        self._publish(EventType.EXECUTION_QUALITY_RECORDED.value, {"order_id": contract.order_id, "market_id": market_id, "quality_score": quality.execution_quality_score})
        return {"dry_run": False, "written": True, "order": _serialize(order_row), "fills": [_serialize(row) for row in fill_rows], "quality": _serialize(quality_row), "precheck": precheck.model_dump(mode="json")}

    def shadow_plan(self, *, market_id: str, strategy_route_id: int | None = None, allocation_id: str | None = None, risk_decision_id: int | None = None, exit_plan_id: str | None = None, dry_run: bool = False, manual_input: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._load_input(market_id, strategy_route_id=strategy_route_id, allocation_id=allocation_id, risk_decision_id=risk_decision_id, manual_input=manual_input)
        precheck = self._precheck_payload(payload, execution_mode="SHADOW_PLAN", exit_plan_id=exit_plan_id)
        if not precheck.allowed:
            return self._blocked(market_id, "SHADOW_PLAN", precheck, dry_run=dry_run)
        contract = self._build_contract(market_id, payload, exit_plan_id=exit_plan_id or "", execution_mode="SHADOW_PLAN", dry_run=dry_run)
        plan = self.shadow.plan(contract)
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "precheck": precheck.model_dump(mode="json"), "order_contract": contract.model_dump(mode="json"), "plan": plan.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                order_row = self.orders.insert(conn, contract, order_status="PLANNED_SHADOW", expires_at=expires_at(contract.ttl_seconds))
                self.order_events.insert(conn, order_id=contract.order_id, event_type="ORDER_CREATED", new_status="CREATED", reason="internal shadow plan contract created", details={"execution_mode": "SHADOW_PLAN"})
                self.order_events.insert(conn, order_id=contract.order_id, event_type="ORDER_PLANNED_SHADOW", old_status="CREATED", new_status="PLANNED_SHADOW", reason=plan.not_sent_reason, details=plan.model_dump(mode="json"))
            conn.commit()
        self._publish(EventType.EXECUTION_ORDER_PLANNED_SHADOW.value, {"order_id": contract.order_id, "market_id": market_id, "not_sent_reason": plan.not_sent_reason})
        return {"dry_run": False, "written": True, "order": _serialize(order_row), "plan": plan.model_dump(mode="json"), "precheck": precheck.model_dump(mode="json")}

    def cancel_evaluate(self, *, order_id: str, current: dict[str, Any] | None = None, dry_run: bool = False) -> dict[str, Any]:
        with self._factory.connect() as conn:
            order = self.orders.by_order_id(conn, order_id)
            if not order:
                raise ExecutionBlocked("order_not_found")
            triggered, reasons = self.cancel_evaluator.evaluate(cancel_if=order.get("cancel_if_json") or {}, current=current or {})
            if dry_run or not triggered:
                return {"dry_run": dry_run, "written": False, "triggered": triggered, "reasons": reasons, "order": _serialize(order)}
            with conn.transaction():
                updated = self.orders.update_status(conn, order_id, "CANCELLED")
                self.order_events.insert(conn, order_id=order_id, event_type="CANCEL_CONDITION_TRIGGERED", old_status=order.get("order_status"), new_status="CANCELLED", reason=",".join(reasons), details={"reasons": reasons})
            conn.commit()
        self._publish(EventType.EXECUTION_CANCEL_CONDITION_TRIGGERED.value, {"order_id": order_id, "reasons": reasons})
        self._publish(EventType.EXECUTION_ORDER_CANCELLED.value, {"order_id": order_id})
        return {"dry_run": False, "written": True, "triggered": True, "reasons": reasons, "order": _serialize(updated)}

    def orders_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.orders.recent(conn, limit)]

    def order_detail(self, order_id: str) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return {"order": _serialize(self.orders.by_order_id(conn, order_id)), "events": [_serialize(row) for row in self.order_events.for_order(conn, order_id)], "fills": [_serialize(row) for row in self.fills.for_order(conn, order_id)], "quality": _serialize(self.quality.for_order(conn, order_id))}

    def fills_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.fills.recent(conn, limit)]

    def errors_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.errors.recent(conn, limit)]

    def quality_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.quality.recent(conn, limit)]

    def _blocked(self, market_id: str, execution_mode: str, precheck: ExecutionPrecheck, *, dry_run: bool) -> dict[str, Any]:
        if dry_run or not self._factory.enabled:
            return {"dry_run": dry_run, "written": False, "blocked": True, "precheck": precheck.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                error = self.errors.insert(conn, market_id=market_id, order_id=None, error_type="EXECUTION_BLOCKED", severity="BLOCKING", message=",".join(precheck.block_reasons), context={"execution_mode": execution_mode, "precheck": precheck.model_dump(mode="json")}, recoverable=True)
            conn.commit()
        self._publish(EventType.EXECUTION_ORDER_BLOCKED.value, {"market_id": market_id, "execution_mode": execution_mode, "block_reasons": precheck.block_reasons})
        self._publish(EventType.EXECUTION_ERROR_RECORDED.value, {"market_id": market_id, "error_type": "EXECUTION_BLOCKED"})
        return {"dry_run": False, "written": True, "blocked": True, "error": _serialize(error), "precheck": precheck.model_dump(mode="json")}

    def _build_contract(self, market_id: str, payload: dict[str, Any], *, exit_plan_id: str, execution_mode: str, dry_run: bool) -> OrderContract:
        return self.builder.build(market_id=market_id, strategy_route=payload["strategy_route"], allocation=payload["capital_allocation"], risk_decision=payload["risk_decision"], exit_plan_id=exit_plan_id, execution_mode=execution_mode, orderbook=payload["orderbook"], liquidity=payload.get("liquidity"), fee=payload.get("fee"), dry_run=dry_run)

    def _precheck_payload(self, payload: dict[str, Any], *, execution_mode: str, exit_plan_id: str | None) -> ExecutionPrecheck:
        route = payload.get("strategy_route") or {}
        allocation = payload.get("capital_allocation") or {}
        risk = payload.get("risk_decision") or {}
        governor = payload.get("governor_state") or {}
        orderbook = payload.get("orderbook") or {}
        liquidity = payload.get("liquidity") or {}
        runtime_mode = str(payload.get("runtime_mode") or self._runtime_mode() or "DATA_ONLY").upper()
        block_reasons: list[str] = []
        if not route:
            block_reasons.append("missing_strategy_route")
        elif str(route.get("route_status") or "").upper() in {"NO_TRADE", "BLOCKED", "INSUFFICIENT_DATA"} or str(route.get("selected_engine") or "").upper() == "NO_TRADE":
            block_reasons.append("strategy_route_not_executable")
        if not allocation:
            block_reasons.append("missing_capital_allocation")
        elif str(allocation.get("allocation_status") or "").upper() not in {"ALLOCATED", "REDUCED"}:
            block_reasons.append("capital_allocation_not_approved")
        if not risk:
            block_reasons.append("missing_risk_approval")
        elif str(risk.get("decision") or "").upper() not in {"APPROVED", "REDUCED"} or not bool(risk.get("approved", False)):
            block_reasons.append("risk_not_approved")
        if not exit_plan_id:
            block_reasons.append("missing_exit_plan")
        if str(governor.get("governor_status") or "OK").upper() not in {"OK", "WARNING"}:
            block_reasons.append("risk_governor_not_ok")
        best_bid = float(orderbook.get("best_bid") or 0.0)
        best_ask = float(orderbook.get("best_ask") or 0.0)
        depth = float(orderbook.get("depth_2c") or orderbook.get("depth_5c") or 0.0)
        if best_bid <= 0 or best_ask <= 0 or not bool(orderbook.get("has_bid_ask", True)):
            block_reasons.append("missing_bid_ask")
        if depth <= 0:
            block_reasons.append("missing_depth")
        max_slippage = float(risk.get("constraints_json", {}).get("max_slippage_bps") if isinstance(risk.get("constraints_json"), dict) else payload.get("max_slippage_bps") or 150.0)
        expected_slippage = float(liquidity.get("expected_slippage_bps") or orderbook.get("spread_bps") or 0.0)
        if expected_slippage > max_slippage:
            block_reasons.append("slippage_too_high")
        if runtime_mode == "KILL":
            block_reasons.append("runtime_kill")
        elif runtime_mode == "DATA_ONLY" and execution_mode == "PAPER_SIM":
            block_reasons.append("data_only_blocks_persisted_execution")
        elif runtime_mode == "PAPER" and execution_mode != "PAPER_SIM":
            block_reasons.append("paper_allows_paper_sim_only")
        elif runtime_mode == "SHADOW_LIVE" and execution_mode != "SHADOW_PLAN":
            block_reasons.append("shadow_live_allows_shadow_plan_only")
        elif runtime_mode in {"SMALL_LIVE", "ATTACK_MODE"}:
            block_reasons.append("live_not_certified")
        elif runtime_mode == "COOLDOWN":
            block_reasons.append("runtime_cooldown")
        allowed_mode = not any(reason in block_reasons for reason in ["runtime_kill", "data_only_blocks_persisted_execution", "paper_allows_paper_sim_only", "shadow_live_allows_shadow_plan_only", "live_not_certified", "runtime_cooldown"])
        return ExecutionPrecheck(
            has_strategy_route=bool(route) and "missing_strategy_route" not in block_reasons,
            has_capital_allocation=bool(allocation) and "missing_capital_allocation" not in block_reasons,
            has_risk_approval=bool(risk) and "missing_risk_approval" not in block_reasons and "risk_not_approved" not in block_reasons,
            has_exit_plan=bool(exit_plan_id),
            governor_ok="risk_governor_not_ok" not in block_reasons,
            has_bid_ask="missing_bid_ask" not in block_reasons,
            has_depth="missing_depth" not in block_reasons,
            slippage_ok="slippage_too_high" not in block_reasons,
            execution_mode_allowed=allowed_mode,
            block_reasons=list(dict.fromkeys(block_reasons)),
        )

    def _load_input(self, market_id: str, *, strategy_route_id: int | None, allocation_id: str | None, risk_decision_id: int | None, manual_input: dict[str, Any] | None) -> dict[str, Any]:
        if manual_input:
            return {
                "runtime_mode": manual_input.get("runtime_mode"),
                "strategy_route": manual_input.get("strategy_route") or {},
                "capital_allocation": manual_input.get("capital_allocation") or {},
                "risk_decision": manual_input.get("risk_decision") or {},
                "governor_state": manual_input.get("governor_state") or {"governor_status": "OK"},
                "orderbook": manual_input.get("orderbook") or {},
                "liquidity": manual_input.get("liquidity") or {},
                "fee": manual_input.get("fee") or {},
                "max_slippage_bps": manual_input.get("max_slippage_bps"),
            }
        with self._factory.connect() as conn:
            return {
                "runtime_mode": self._runtime_mode(),
                "strategy_route": _latest_route(conn, market_id, strategy_route_id) or {},
                "capital_allocation": _latest_allocation(conn, market_id, allocation_id) or {},
                "risk_decision": _latest_risk_decision(conn, market_id, risk_decision_id) or {},
                "governor_state": _latest_any(conn, "risk_governor_state", None, order_by="updated_at") or {"governor_status": "INSUFFICIENT_DATA"},
                "orderbook": _latest_any(conn, "orderbook_signals", market_id, order_by="ts") or {},
                "liquidity": _latest_any(conn, "liquidity_signals", market_id, order_by="ts") or {},
                "fee": _latest_any(conn, "fee_reward_signals", market_id, order_by="ts") or {},
            }

    def _runtime_mode(self) -> str:
        try:
            return self._state_governor.get_current_state().current_mode.value
        except Exception:
            return "DATA_ONLY"

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type, payload, "execution_v2", aggregate_type="execution_v2", aggregate_id=payload.get("order_id") or payload.get("market_id") or "execution_v2")


def _exists(conn: Connection, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _latest_any(conn: Connection, table: str, market_id: str | None, *, order_by: str = "created_at") -> dict[str, Any] | None:
    if not _exists(conn, table):
        return None
    if market_id is None:
        row = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by} DESC, id DESC LIMIT 1").fetchone()
    else:
        row = conn.execute(f"SELECT * FROM {table} WHERE market_id=%s ORDER BY {order_by} DESC, id DESC LIMIT 1", (market_id,)).fetchone()
    return dict(row) if row else None


def _latest_route(conn: Connection, market_id: str, row_id: int | None) -> dict[str, Any] | None:
    if not _exists(conn, "strategy_routes_v2"):
        return None
    if row_id:
        row = conn.execute("SELECT * FROM strategy_routes_v2 WHERE id=%s LIMIT 1", (row_id,)).fetchone()
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


def _latest_risk_decision(conn: Connection, market_id: str, row_id: int | None) -> dict[str, Any] | None:
    if not _exists(conn, "risk_gate_decisions"):
        return None
    if row_id:
        row = conn.execute("SELECT * FROM risk_gate_decisions WHERE id=%s LIMIT 1", (row_id,)).fetchone()
    else:
        row = conn.execute("SELECT * FROM risk_gate_decisions WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()
    return dict(row) if row else None


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    output = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            output[key] = value.isoformat()
        elif isinstance(value, bool):
            output[key] = value
        elif hasattr(value, "__float__"):
            try:
                output[key] = float(value)
            except Exception:
                output[key] = value
        else:
            output[key] = value
    return output


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _empty(status: str) -> dict[str, Any]:
    return {"status": status, "orders_today": 0, "paper_orders_today": 0, "shadow_plans_today": 0, "fills_today": 0, "partial_fills_today": 0, "failed_fills_today": 0, "cancelled_today": 0, "avg_slippage_bps": None, "avg_quality_score": None, "errors_today": 0, "live_certified": False}
