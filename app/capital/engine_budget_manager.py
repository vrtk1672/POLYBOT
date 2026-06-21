from __future__ import annotations

from app.capital.contracts import CapitalState, EngineBudget
from app.capital.loss_streak_policy import LossStreakPolicy


DEFAULT_BUCKETS = {
    "SAFE": "SAFE_CAPITAL",
    "STRIKE": "STRIKE_CAPITAL",
    "CONVEX": "CONVEX_CAPITAL",
    "MAKER": "MAKER_CAPITAL",
    "HUNT": "HUNT_CAPITAL",
    "MOONSHOT_BASKET": "MOONSHOT_BASKET",
    "REINVEST": "PROFIT_POCKET",
    "NO_TRADE": "CASH_RESERVE",
}


class EngineBudgetManager:
    def __init__(self, *, loss_policy: LossStreakPolicy | None = None) -> None:
        self.loss_policy = loss_policy or LossStreakPolicy()

    def build_default_budgets(self, state: CapitalState) -> list[EngineBudget]:
        available_risk_capital = max(
            state.available_capital_usd - state.survival_reserve_usd - state.cash_reserve_usd,
            0.0,
        )
        attack_available = max(state.attack_bank_usd, 0.0)
        profit_available = max(state.profit_pocket_usd, 0.0)
        specs = {
            "SAFE": (0.30, 0.10, 0.05),
            "STRIKE": (0.18, 0.08, 0.04),
            "CONVEX": (0.12, 0.04, 0.025),
            "MAKER": (0.16, 0.06, 0.03),
            "HUNT": (0.05, 0.025, 0.02),
            "MOONSHOT_BASKET": (0.04, 0.015, 0.01),
            "REINVEST": (0.0, 0.0, 0.0),
            "NO_TRADE": (0.0, 0.0, 0.0),
        }
        budgets: list[EngineBudget] = []
        for engine, (budget_pct, position_pct, loss_pct) in specs.items():
            budget_source = profit_available if engine == "REINVEST" else available_risk_capital
            budget = max(budget_source * budget_pct, 0.0)
            if engine in {"HUNT", "MOONSHOT_BASKET"} and attack_available > 0:
                budget = min(max(budget, attack_available), attack_available)
            multiplier = self.loss_policy.multiplier(engine=engine, loss_streak_count=state.loss_streak_count)
            budgets.append(
                EngineBudget(
                    engine=engine,  # type: ignore[arg-type]
                    bucket=DEFAULT_BUCKETS[engine],  # type: ignore[arg-type]
                    budget_usd=round(budget, 6),
                    available_usd=round(budget, 6),
                    max_position_usd=round(available_risk_capital * position_pct * multiplier, 6),
                    max_loss_usd=round(available_risk_capital * loss_pct * multiplier, 6),
                    max_open_allocations=1 if engine in {"HUNT", "CONVEX"} else 3,
                    enabled=engine != "NO_TRADE" and budget > 0 and multiplier > 0,
                    cooldown_active=False,
                    loss_streak_multiplier=multiplier,
                    policy={
                        "budget_pct": budget_pct,
                        "position_pct": position_pct,
                        "max_loss_pct": loss_pct,
                        "internal_decision_only": True,
                    },
                )
            )
        return budgets

    def choose_budget(self, engine: str, budgets: list[EngineBudget], state: CapitalState) -> EngineBudget | None:
        engine = str(engine or "").upper()
        candidates = [budget for budget in budgets if budget.engine == engine]
        if not candidates:
            return None
        budget = candidates[0]
        if engine in {"CONVEX", "HUNT", "MOONSHOT_BASKET"} and state.attack_bank_usd > 0:
            budget.bucket = "ATTACK_BANK"  # type: ignore[assignment]
            budget.available_usd = min(budget.available_usd, state.attack_bank_usd)
            budget.budget_usd = min(budget.budget_usd, state.attack_bank_usd)
        return budget

