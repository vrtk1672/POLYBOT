from __future__ import annotations

from app.brains.contracts import CapitalBrainInput, CapitalBrainOutput, bounded


class CapitalRecommendationBuilder:
    def build(self, payload: CapitalBrainInput) -> CapitalBrainOutput:
        reasons = list(payload.insufficient_data_reasons)
        constraints: list[str] = []
        if payload.available_capital is None:
            reasons.append("missing_available_capital")
        if payload.balance is None:
            reasons.append("missing_balance")
        if payload.risk_limits.get("strict_mode", 0) and not payload.risk_limits:
            reasons.append("missing_risk_limits")
        if reasons:
            return CapitalBrainOutput(
                market_id=payload.market_id,
                capital_allowed=False,
                block_reason="insufficient_capital_data",
                insufficient_data=True,
                insufficient_data_reasons=reasons,
                allocation_reason="Capital data is insufficient; no allocation recommendation can be made.",
                constraints=constraints,
            )

        balance = float(payload.balance or 0)
        available = float(payload.available_capital or 0)
        locked = float(payload.locked_capital or 0)
        open_exposure = sum(float(row.get("notional_usd") or row.get("size_usd") or 0) for row in payload.open_positions)
        reserve_pct = float(payload.risk_limits.get("min_cash_reserve_pct", 0.2))
        max_alloc_pct = float(payload.risk_limits.get("max_alloc_pct", 0.05))
        max_exposure_pct = float(payload.risk_limits.get("max_open_exposure_pct", 0.5))
        reserve_target = balance * reserve_pct
        deployable = max(0.0, available - reserve_target)
        engine = payload.candidate_engine or "UNKNOWN"
        engine_budget = payload.engine_budgets.get(engine)
        if engine_budget is None and payload.engine_budgets:
            engine_budget = 0.0
        engine_budget = available if engine_budget is None else float(engine_budget)
        slippage_risk = _memory_slippage_risk(payload.memory_snapshot)
        memory_confidence = bounded(payload.memory_snapshot.get("confidence") or payload.memory_snapshot.get("memory_confidence"))

        if available <= reserve_target:
            constraints.append("cash_reserve_too_low")
        if engine_budget <= 0:
            constraints.append("engine_budget_exhausted")
        if open_exposure >= balance * max_exposure_pct:
            constraints.append("open_exposure_too_high")
        if slippage_risk >= 0.7:
            constraints.append("unsafe_slippage_memory")
        max_by_policy = balance * max_alloc_pct
        max_size = max(0.0, min(deployable, engine_budget, max_by_policy) * (1 - min(slippage_risk, 0.8)))
        allowed = max_size > 0 and not constraints
        confidence = bounded((0.35 + memory_confidence * 0.3 + payload.data_completeness_score * 0.35) * (1 - slippage_risk * 0.4))
        block_reason = constraints[0] if constraints else None
        return CapitalBrainOutput(
            market_id=payload.market_id,
            capital_allowed=allowed,
            block_reason=block_reason,
            max_position_size_usd=max_size if allowed else 0.0,
            risk_budget_usd=max_size if allowed else 0.0,
            capital_bucket=engine.lower() if allowed else None,
            cash_reserve_after_usd=max(0.0, available - max_size),
            engine_budget_remaining_usd=max(0.0, engine_budget - max_size),
            allocation_confidence=confidence if allowed else min(confidence, 0.2),
            allocation_reason="Capital could be reserved for future opportunity review." if allowed else f"Capital blocked: {block_reason or 'insufficient_data'}",
            insufficient_data=False,
            available_capital_usd=available,
            locked_capital_usd=locked,
            open_exposure_usd=open_exposure,
            capital_recycling_score=payload.capital_recycling_speed,
            constraints=constraints,
        )


def _memory_slippage_risk(memory: dict) -> float:
    if not memory:
        return 0.0
    if "slippage_memory" in memory and isinstance(memory["slippage_memory"], list) and memory["slippage_memory"]:
        return bounded(memory["slippage_memory"][0].get("slippage_risk_score"))
    return bounded(memory.get("slippage_risk_score"))
