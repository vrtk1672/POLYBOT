from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class ConvexEngine:
    name = "CONVEX"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if component(payload, "convexity") < 0.65:
            reasons.append("convex_requires_asymmetric_upside")
        if component(payload, "risk_penalty") > 0.55 or component(payload, "trap_risk") > 0.55:
            reasons.append("convex_rejects_undefined_downside")
        if component(payload, "liquidity_quality") < 0.35:
            reasons.append("convex_requires_small_size_liquidity")
        if component(payload, "wording_risk") > 0.7:
            reasons.append("convex_rejects_wording_trap")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING" if reasons[0] in hard_blocks(payload) else "WARNING")
        score = min(1.0, component(payload, "convexity") * 0.4 + payload.opportunity_score * 0.3 + component(payload, "trigger_strength") * 0.15 + component(payload, "liquidity_quality") * 0.15)
        return EngineDecision(
            engine=self.name,
            eligible=True,
            engine_score=score,
            confidence=component(payload, "confidence"),
            contract=self.contracts.build(payload, engine=self.name, reason="Asymmetric upside with defined contract-only downside and small-size limits.", entry_mode="SMALL_LIMIT_CONTRACT", exit_mode="TARGET_STOP_TIME_CONTRACT", max_hold_minutes=720, max_position_size_usd=100.0, max_loss_fraction=0.2),
        )

