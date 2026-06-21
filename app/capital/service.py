from __future__ import annotations

from typing import Any
from uuid import uuid4
from decimal import Decimal

from psycopg import Connection

from app.capital.capital_allocator import CapitalAllocatorV2
from app.capital.capital_errors import CapitalAllocationBlocked
from app.capital.capital_state_builder import CapitalStateBuilder
from app.capital.contracts import CapitalAllocationRequest, CapitalState, EngineBudget
from app.capital.engine_budget_manager import EngineBudgetManager
from app.capital.reinvest_brain import ReinvestBrain
from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.attack_bank_repository import AttackBankRepository
from app.repositories.capital_allocation_repository import CapitalAllocationRepository
from app.repositories.capital_event_repository import CapitalEventRepository
from app.repositories.capital_state_repository import CapitalStateRepository
from app.repositories.engine_budget_repository import EngineBudgetRepository
from app.repositories.profit_pocket_repository import ProfitPocketRepository
from app.repositories.reinvest_ledger_repository import ReinvestLedgerRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class CapitalService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.state_builder = CapitalStateBuilder()
        self.budget_manager = EngineBudgetManager()
        self.allocator = CapitalAllocatorV2()
        self.reinvest_brain = ReinvestBrain()
        self.state_repo = CapitalStateRepository()
        self.budget_repo = EngineBudgetRepository()
        self.allocation_repo = CapitalAllocationRepository()
        self.ledger_repo = ReinvestLedgerRepository()
        self.pocket_repo = ProfitPocketRepository()
        self.attack_repo = AttackBankRepository()
        self.event_repo = CapitalEventRepository()

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return _empty("DISABLED")
        try:
            with self._factory.connect() as conn:
                if not _exists(conn, "capital_state_v2"):
                    return _empty("EMPTY")
                state = conn.execute("SELECT MAX(created_at) AS latest_state_ts FROM capital_state_v2").fetchone()
                allocations = conn.execute(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE) AS allocations_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND allocation_status = 'BLOCKED') AS blocked_today,
                      COUNT(*) FILTER (WHERE created_at::date = CURRENT_DATE AND allocation_status = 'REDUCED') AS reduced_today,
                      COUNT(*) FILTER (WHERE allocation_status = 'INSUFFICIENT_DATA') AS insufficient_data_count
                    FROM capital_allocations_v2
                    """
                ).fetchone()
                attack = self.attack_repo.latest(conn) or {}
                pocket = self.pocket_repo.latest(conn) or {}
            return {
                "status": "HEALTHY" if state and state.get("latest_state_ts") else "EMPTY",
                "latest_state_ts": _iso((state or {}).get("latest_state_ts")),
                "allocations_today": int((allocations or {}).get("allocations_today") or 0),
                "blocked_today": int((allocations or {}).get("blocked_today") or 0),
                "reduced_today": int((allocations or {}).get("reduced_today") or 0),
                "insufficient_data_count": int((allocations or {}).get("insufficient_data_count") or 0),
                "attack_bank_available": float((attack or {}).get("available_usd") or 0),
                "profit_pocket_available": float((pocket or {}).get("available_profit_usd") or 0),
                "errors_today": 0,
            }
        except Exception as exc:
            data = _empty("ERROR")
            data["errors_today"] = 1
            data["error"] = str(exc)
            return data

    def rebuild_state(self, *, dry_run: bool = False, manual_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_allowed()
        state = self.state_builder.build(runtime_mode=self._runtime_mode(), manual_payload=manual_payload)
        budgets = self.budget_manager.build_default_budgets(state)
        if dry_run or not self._factory.enabled:
            return {"dry_run": True, "written": False, "state": state.model_dump(mode="json"), "budgets": [b.model_dump(mode="json") for b in budgets]}
        with self._factory.connect() as conn:
            with conn.transaction():
                row = self.state_repo.insert(conn, state)
                budget_rows = self.budget_repo.upsert_many(conn, budgets)
                if state.profit_pocket_usd >= 0:
                    self.pocket_repo.upsert(conn, pocket_id="profit_pocket_default", totals={
                        "total_realized_profit_usd": state.profit_pocket_usd,
                        "available_profit_usd": state.profit_pocket_usd,
                        "reserved_profit_usd": 0.0,
                        "withdrawn_profit_usd": 0.0,
                        "reinvested_profit_usd": 0.0,
                    }, source_type=state.source_type, confidence=state.data_confidence)
                if state.attack_bank_usd >= 0:
                    self.attack_repo.upsert(conn, attack_bank_id="attack_bank_default", values={
                        "available_usd": state.attack_bank_usd,
                        "reserved_usd": 0.0,
                        "used_usd": 0.0,
                        "realized_profit_funded_usd": state.attack_bank_usd,
                        "base_capital_used_usd": 0.0,
                        "max_attack_allocation_usd": state.attack_bank_usd * 0.5,
                    }, enabled=state.attack_bank_usd > 0)
                self.event_repo.insert(
                    conn,
                    event_id=f"capital_event_{uuid4().hex}",
                    event_type="capital.state.created",
                    actor="capital_service",
                    reason="capital state rebuilt from DB or explicit smoke input",
                    after=state.model_dump(mode="json"),
                    correlation_id=state.state_id,
                )
            conn.commit()
        self._publish(EventType.CAPITAL_STATE_CREATED.value, {"state_id": state.state_id, "insufficient_data": state.insufficient_data})
        for budget in budgets:
            self._publish(EventType.ENGINE_BUDGET_UPDATED.value, {"engine": budget.engine, "bucket": budget.bucket, "available_usd": budget.available_usd})
        return {"dry_run": False, "written": True, "state": _serialize(row), "budgets": [_serialize(row) for row in budget_rows]}

    def allocate(
        self,
        *,
        market_id: str,
        strategy_route_id: int | None = None,
        requested_size_usd: float | None = None,
        dry_run: bool = False,
        manual_route: dict[str, Any] | None = None,
        manual_capital: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._assert_allowed()
        if not self._factory.enabled and manual_route is not None:
            state = self.state_builder.build(runtime_mode=self._runtime_mode(), manual_payload=manual_capital or {})
            budgets = self.budget_manager.build_default_budgets(state)
            request = self._request_from_route(manual_route, requested_size_usd=requested_size_usd, dry_run=True)
            decision = self.allocator.allocate(request, state, budgets)
            return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json")}
        with self._factory.connect() as conn:
            route = manual_route or self._load_route(conn, market_id=market_id, strategy_route_id=strategy_route_id)
            if not route:
                state = self._latest_or_built_state(conn, manual_capital=manual_capital)
                decision = self.allocator.allocate(
                    CapitalAllocationRequest(market_id=market_id, engine="NO_TRADE", route_status="INSUFFICIENT_DATA", requested_size_usd=requested_size_usd or 0),
                    state,
                    self._budgets(conn, state),
                )
                decision.allocation_status = "INSUFFICIENT_DATA"
                decision.rejection_reason = "missing_strategy_route"
                return self._maybe_write_decision(conn, decision, dry_run=dry_run)
            state = self._latest_or_built_state(conn, manual_capital=manual_capital)
            budgets = self._budgets(conn, state)
            request = self._request_from_route(route, requested_size_usd=requested_size_usd, dry_run=dry_run)
            decision = self.allocator.allocate(request, state, budgets)
            return self._maybe_write_decision(conn, decision, dry_run=dry_run)

    def evaluate_reinvest(self, *, dry_run: bool = False, realized_profit_usd: float | None = None) -> dict[str, Any]:
        self._assert_allowed()
        decision = self.reinvest_brain.evaluate(realized_profit_usd=realized_profit_usd, dry_run=dry_run)
        if dry_run or not decision.allowed:
            return {"dry_run": dry_run, "written": False, "decision": decision.model_dump(mode="json")}
        with self._factory.connect() as conn:
            with conn.transaction():
                pocket = self.pocket_repo.upsert(
                    conn,
                    pocket_id="profit_pocket_default",
                    totals={
                        "total_realized_profit_usd": realized_profit_usd or 0.0,
                        "available_profit_usd": max((realized_profit_usd or 0.0) - decision.amount_usd, 0.0),
                        "reserved_profit_usd": 0.0,
                        "withdrawn_profit_usd": 0.0,
                        "reinvested_profit_usd": decision.amount_usd,
                    },
                    source_type="REALIZED_PROFIT_SMOKE",
                )
                attack = self.attack_repo.upsert(
                    conn,
                    attack_bank_id="attack_bank_default",
                    values={
                        "available_usd": decision.amount_usd,
                        "reserved_usd": 0.0,
                        "used_usd": 0.0,
                        "realized_profit_funded_usd": decision.amount_usd,
                        "base_capital_used_usd": 0.0,
                        "max_attack_allocation_usd": decision.amount_usd * 0.5,
                    },
                    enabled=True,
                    policy=decision.policy,
                )
                ledger = self.ledger_repo.insert(
                    conn,
                    ledger_id=f"reinvest_{uuid4().hex}",
                    event_type=decision.event_type,
                    amount_usd=decision.amount_usd,
                    from_bucket=decision.from_bucket,
                    to_bucket=decision.to_bucket,
                    reason=decision.reason,
                    policy=decision.policy,
                    realized_profit_usd=realized_profit_usd,
                )
                self.event_repo.insert(
                    conn,
                    event_id=f"capital_event_{uuid4().hex}",
                    event_type="reinvest.attack_bank.updated",
                    actor="capital_service",
                    reason=decision.reason,
                    bucket="ATTACK_BANK",
                    amount_usd=decision.amount_usd,
                    after={"profit_pocket": _serialize(pocket), "attack_bank": _serialize(attack)},
                    correlation_id=ledger["ledger_id"],
                )
            conn.commit()
        self._publish(EventType.REINVEST_PROFIT_POCKET_UPDATED.value, {"amount_usd": decision.amount_usd})
        self._publish(EventType.REINVEST_ATTACK_BANK_UPDATED.value, {"amount_usd": decision.amount_usd, "base_capital_used_usd": 0})
        return {"dry_run": False, "written": True, "decision": decision.model_dump(mode="json")}

    def latest_state(self) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return _serialize(self.state_repo.latest(conn)) or {"state": None}

    def budgets(self) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.budget_repo.list(conn)]

    def allocations_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.allocation_repo.recent(conn, limit=limit)]

    def events_recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._factory.connect() as conn:
            return [_serialize(row) for row in self.event_repo.recent(conn, limit=limit)]

    def reinvest_summary(self) -> dict[str, Any]:
        with self._factory.connect() as conn:
            return {
                "profit_pocket": _serialize(self.pocket_repo.latest(conn)),
                "attack_bank": _serialize(self.attack_repo.latest(conn)),
                "ledger": [_serialize(row) for row in self.ledger_repo.recent(conn)],
            }

    def _maybe_write_decision(self, conn: Connection, decision, *, dry_run: bool) -> dict[str, Any]:
        if dry_run:
            decision.dry_run = True
            decision.allocation_status = "DRY_RUN"
            return {"dry_run": True, "written": False, "decision": decision.model_dump(mode="json")}
        with conn.transaction():
            row = self.allocation_repo.insert(conn, decision)
            event_type = "capital.allocation.created"
            if decision.allocation_status == "BLOCKED":
                event_type = "capital.allocation.blocked"
            elif decision.allocation_status == "REDUCED":
                event_type = "capital.allocation.reduced"
            self.event_repo.insert(
                conn,
                event_id=f"capital_event_{uuid4().hex}",
                event_type=event_type,
                actor="capital_service",
                market_id=decision.market_id,
                engine=decision.engine,
                bucket=decision.bucket,
                amount_usd=decision.approved_size_usd,
                reason=decision.allocation_reason or decision.rejection_reason or "capital allocation decision",
                after=decision.model_dump(mode="json"),
                correlation_id=decision.allocation_id,
            )
        conn.commit()
        event = EventType.CAPITAL_ALLOCATION_CREATED
        if decision.allocation_status == "BLOCKED":
            event = EventType.CAPITAL_ALLOCATION_BLOCKED
        elif decision.allocation_status == "REDUCED":
            event = EventType.CAPITAL_ALLOCATION_REDUCED
        self._publish(event.value, {"allocation_id": decision.allocation_id, "market_id": decision.market_id, "engine": decision.engine, "status": decision.allocation_status})
        return {"dry_run": False, "written": True, "decision": _serialize(row)}

    def _latest_or_built_state(self, conn: Connection, *, manual_capital: dict[str, Any] | None) -> CapitalState:
        if manual_capital is not None:
            return self.state_builder.build(runtime_mode=self._runtime_mode(), manual_payload=manual_capital)
        latest = self.state_repo.latest(conn)
        if latest:
            return _state_from_row(latest)
        return self.state_builder.build(runtime_mode=self._runtime_mode())

    def _budgets(self, conn: Connection, state: CapitalState) -> list[EngineBudget]:
        rows = self.budget_repo.list(conn) if _exists(conn, "engine_budgets") else []
        if rows:
            return [_budget_from_row(row) for row in rows]
        return self.budget_manager.build_default_budgets(state)

    def _request_from_route(self, route: dict[str, Any], *, requested_size_usd: float | None, dry_run: bool) -> CapitalAllocationRequest:
        contract = route.get("engine_contract_json") or {}
        requested = requested_size_usd if requested_size_usd is not None else route.get("max_position_size_usd") or contract.get("max_position_size_usd") or 0
        return CapitalAllocationRequest(
            market_id=route["market_id"],
            market_family=route.get("market_family"),
            side=route.get("side") or "UNKNOWN",
            engine=route.get("selected_engine") or "NO_TRADE",
            strategy_route_id=route.get("id"),
            strategy_run_id=route.get("run_id"),
            requested_size_usd=requested,
            max_loss_usd=route.get("max_loss_usd") or contract.get("max_loss_usd") or 0,
            expected_hold_minutes=route.get("max_hold_minutes") or contract.get("expected_hold_minutes") or 0,
            route_confidence=route.get("route_confidence") or 0,
            route_status=route.get("route_status") or "UNKNOWN",
            dry_run=dry_run,
            route=route,
        )

    def _load_route(self, conn: Connection, *, market_id: str, strategy_route_id: int | None) -> dict[str, Any] | None:
        if not _exists(conn, "strategy_routes_v2"):
            return None
        if strategy_route_id is not None:
            row = conn.execute("SELECT * FROM strategy_routes_v2 WHERE id=%s LIMIT 1", (strategy_route_id,)).fetchone()
        else:
            row = conn.execute("SELECT * FROM strategy_routes_v2 WHERE market_id=%s ORDER BY created_at DESC, id DESC LIMIT 1", (market_id,)).fetchone()
        return dict(row) if row else None

    def _assert_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.SCORE_MARKET)
        except Exception as exc:
            raise CapitalAllocationBlocked("capital allocation blocked by runtime mode") from exc

    def _runtime_mode(self) -> str | None:
        try:
            return self._governor.get_current_state().current_mode.value
        except Exception:
            return None

    def _publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_bus.publish(event_type, payload, "capital", aggregate_type="capital", aggregate_id=payload.get("market_id") or payload.get("state_id") or "capital")


def _state_from_row(row: dict[str, Any]) -> CapitalState:
    return CapitalState(
        state_id=row["state_id"],
        runtime_mode=row.get("runtime_mode"),
        total_capital_usd=row.get("total_capital_usd"),
        base_capital_usd=row.get("base_capital_usd"),
        available_capital_usd=row.get("available_capital_usd"),
        locked_capital_usd=row.get("locked_capital_usd"),
        open_exposure_usd=row.get("open_exposure_usd"),
        survival_reserve_usd=row.get("survival_reserve_usd"),
        cash_reserve_usd=row.get("cash_reserve_usd"),
        profit_pocket_usd=row.get("profit_pocket_usd"),
        attack_bank_usd=row.get("attack_bank_usd"),
        realized_pnl_usd=row.get("realized_pnl_usd"),
        unrealized_pnl_usd=row.get("unrealized_pnl_usd"),
        loss_streak_count=row.get("loss_streak_count") or 0,
        win_streak_count=row.get("win_streak_count") or 0,
        source_type=row.get("source_type") or "DB",
        source_ref=row.get("source_ref"),
        data_confidence=row.get("data_confidence") or 0,
        insufficient_data=row.get("insufficient_data") or False,
        insufficient_data_reasons=row.get("insufficient_data_reasons_json") or [],
    )


def _budget_from_row(row: dict[str, Any]) -> EngineBudget:
    return EngineBudget(
        engine=row["engine"],
        bucket=row["bucket"],
        budget_usd=row.get("budget_usd") or 0,
        used_usd=row.get("used_usd") or 0,
        reserved_usd=row.get("reserved_usd") or 0,
        available_usd=row.get("available_usd") or 0,
        max_position_usd=row.get("max_position_usd") or 0,
        max_loss_usd=row.get("max_loss_usd") or 0,
        max_open_allocations=row.get("max_open_allocations") or 1,
        cooldown_active=row.get("cooldown_active") or False,
        loss_streak_multiplier=row.get("loss_streak_multiplier") or 1,
        enabled=row.get("enabled") if row.get("enabled") is not None else True,
        policy=row.get("policy_json") or {},
    )


def _exists(conn: Connection, table: str) -> bool:
    return conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is not None


def _empty(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "latest_state_ts": None,
        "allocations_today": 0,
        "blocked_today": 0,
        "reduced_today": 0,
        "insufficient_data_count": 0,
        "attack_bank_available": 0.0,
        "profit_pocket_available": 0.0,
        "errors_today": 0,
    }


def _iso(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
