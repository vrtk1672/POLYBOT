from __future__ import annotations

from app.capital.contracts import CapitalAllocationDecision, CapitalAllocationRequest, CapitalState, EngineBudget
from app.capital.engine_budget_manager import EngineBudgetManager
from app.capital.loss_streak_policy import LossStreakPolicy


class AllocationPolicy:
    def __init__(self, *, budget_manager: EngineBudgetManager | None = None, loss_policy: LossStreakPolicy | None = None) -> None:
        self.budget_manager = budget_manager or EngineBudgetManager()
        self.loss_policy = loss_policy or LossStreakPolicy()

    def decide(
        self,
        request: CapitalAllocationRequest,
        state: CapitalState,
        budgets: list[EngineBudget],
    ) -> CapitalAllocationDecision:
        if request.dry_run:
            dry_decision = self.decide(request.model_copy(update={"dry_run": False}), state, budgets)
            dry_decision.dry_run = True
            dry_decision.allocation_status = "DRY_RUN"
            return dry_decision
        if state.insufficient_data:
            return self._blocked(request, "INSUFFICIENT_DATA", "missing_capital_data", state=state)
        if request.engine == "NO_TRADE" or request.route_status in {"NO_TRADE", "BLOCKED", "INSUFFICIENT_DATA"}:
            return self._blocked(request, "BLOCKED", "strategy_route_not_allocatable", state=state)
        budget = self.budget_manager.choose_budget(request.engine, budgets, state)
        if budget is None:
            return self._blocked(request, "INSUFFICIENT_DATA", "missing_engine_budget", state=state)
        if not budget.enabled or budget.cooldown_active:
            return self._blocked(request, "BLOCKED", "engine_budget_unavailable", state=state, budget=budget)
        if self.loss_policy.blocks(engine=request.engine, loss_streak_count=state.loss_streak_count):
            return self._blocked(request, "BLOCKED", "loss_streak_blocks_aggressive_engine", state=state, budget=budget)

        requested = request.requested_size_usd or float(request.route.get("max_position_size_usd") or 0.0)
        if requested <= 0:
            return self._blocked(request, "INSUFFICIENT_DATA", "missing_requested_size", state=state, budget=budget)
        reserve_floor = state.survival_reserve_usd + state.cash_reserve_usd
        reserve_headroom = max(state.available_capital_usd - reserve_floor, 0.0)
        multiplier = self.loss_policy.multiplier(engine=request.engine, loss_streak_count=state.loss_streak_count)
        aggressive_cap = self._aggressive_cap(request.engine, state, requested)
        approved = min(requested, budget.available_usd, budget.max_position_usd, reserve_headroom, aggressive_cap)
        approved = round(max(approved * multiplier, 0.0), 6)
        if approved <= 0:
            return self._blocked(request, "BLOCKED", "reserve_or_budget_exhausted", state=state, budget=budget)

        status = "ALLOCATED" if approved >= requested else "REDUCED"
        max_loss = round(min(request.max_loss_usd or budget.max_loss_usd, budget.max_loss_usd, approved), 6)
        attack_bank_used = approved if budget.bucket == "ATTACK_BANK" else 0.0
        profit_pocket_used = approved if budget.bucket == "PROFIT_POCKET" else 0.0
        base_capital_used = 0.0 if budget.bucket == "ATTACK_BANK" else approved
        if budget.bucket == "ATTACK_BANK":
            base_capital_used = 0.0
        return CapitalAllocationDecision(
            market_id=request.market_id,
            market_family=request.market_family,
            side=request.side,
            engine=request.engine,
            bucket=budget.bucket,
            allocation_status=status,  # type: ignore[arg-type]
            requested_size_usd=requested,
            approved_size_usd=approved,
            max_loss_usd=max_loss,
            reserve_after_usd=round(max(state.available_capital_usd - approved, 0.0), 6),
            engine_budget_before_usd=budget.available_usd,
            engine_budget_after_usd=round(max(budget.available_usd - approved, 0.0), 6),
            attack_bank_used_usd=attack_bank_used,
            profit_pocket_used_usd=profit_pocket_used,
            base_capital_used_usd=base_capital_used,
            allocation_reason="capital_policy_approved" if status == "ALLOCATED" else "capital_policy_reduced_size",
            constraints={
                "survival_reserve_usd": state.survival_reserve_usd,
                "cash_reserve_usd": state.cash_reserve_usd,
                "reserve_floor_usd": reserve_floor,
                "loss_streak_multiplier": multiplier,
                "internal_decision_only": True,
                "not_executable_order": True,
            },
            strategy_route_id=request.strategy_route_id,
            strategy_run_id=request.strategy_run_id,
        )

    def _blocked(
        self,
        request: CapitalAllocationRequest,
        status: str,
        reason: str,
        *,
        state: CapitalState,
        budget: EngineBudget | None = None,
    ) -> CapitalAllocationDecision:
        return CapitalAllocationDecision(
            market_id=request.market_id,
            market_family=request.market_family,
            side=request.side,
            engine=request.engine,
            bucket=budget.bucket if budget and request.engine != "NO_TRADE" else None,
            allocation_status=status,  # type: ignore[arg-type]
            requested_size_usd=request.requested_size_usd,
            approved_size_usd=0.0,
            max_loss_usd=0.0,
            reserve_after_usd=state.available_capital_usd,
            engine_budget_before_usd=budget.available_usd if budget else 0.0,
            engine_budget_after_usd=budget.available_usd if budget else 0.0,
            allocation_reason="capital_policy_blocked",
            rejection_reason=reason,
            constraints={
                "survival_reserve_usd": state.survival_reserve_usd,
                "cash_reserve_usd": state.cash_reserve_usd,
                "internal_decision_only": True,
                "not_executable_order": True,
            },
            strategy_route_id=request.strategy_route_id,
            strategy_run_id=request.strategy_run_id,
        )

    @staticmethod
    def _aggressive_cap(engine: str, state: CapitalState, requested: float) -> float:
        engine = str(engine or "").upper()
        if engine == "MOONSHOT_BASKET":
            return min(requested, max(state.available_capital_usd * 0.02, 0.0), 50.0)
        if engine == "HUNT":
            return min(requested, max(state.available_capital_usd * 0.05, 0.0), max(state.attack_bank_usd, 25.0))
        if engine == "CONVEX":
            return min(requested, max(state.available_capital_usd * 0.08, 0.0))
        return requested

