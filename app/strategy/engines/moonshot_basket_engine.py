from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class MoonshotBasketEngine:
    name = "MOONSHOT_BASKET"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if component(payload, "convexity") < 0.8:
            reasons.append("moonshot_requires_extreme_convexity")
        if component(payload, "risk_penalty") > 0.65 or component(payload, "wording_risk") > 0.55:
            reasons.append("moonshot_rejects_trap_or_wording_risk")
        if component(payload, "liquidity_quality") < 0.25:
            reasons.append("moonshot_requires_minimum_small_size_liquidity")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING" if reasons[0] in hard_blocks(payload) else "WARNING")
        score = min(1.0, component(payload, "convexity") * 0.55 + payload.opportunity_score * 0.25 + component(payload, "liquidity_quality") * 0.2)
        contract = self.contracts.build(payload, engine=self.name, reason="Small basket-style convex long-shot candidate; no averaging down and no capital reserved.", entry_mode="TINY_LIMIT_CONTRACT", exit_mode="BASKET_TARGET_STOP_CONTRACT", max_hold_minutes=1440, max_position_size_usd=25.0, max_loss_fraction=1.0)
        contract.position_sizing_rules.update({"basket_sizing": True, "max_candidate_weight": 0.05, "no_averaging_down": True})
        return EngineDecision(engine=self.name, eligible=True, engine_score=score, confidence=min(component(payload, "confidence"), 0.65), contract=contract)

