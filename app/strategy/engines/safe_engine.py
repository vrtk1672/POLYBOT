from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class SafeEngine:
    name = "SAFE"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if payload.opportunity_score < 0.62 or component(payload, "confidence") < 0.72:
            reasons.append("safe_requires_high_confidence")
        if component(payload, "wording_risk") > 0.22:
            reasons.append("safe_rejects_high_wording_risk")
        if component(payload, "liquidity_quality") < 0.7 or component(payload, "exit_probability") < 0.7:
            reasons.append("safe_requires_strong_liquidity")
        if component(payload, "risk_penalty") > 0.3 or component(payload, "trap_risk") > 0.25:
            reasons.append("safe_rejects_high_risk")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING" if reasons[0] in hard_blocks(payload) else "WARNING")
        score = min(1.0, payload.opportunity_score * 0.6 + component(payload, "confidence") * 0.25 + component(payload, "liquidity_quality") * 0.15)
        return EngineDecision(
            engine=self.name,
            eligible=True,
            engine_score=score,
            confidence=component(payload, "confidence"),
            contract=self.contracts.build(payload, engine=self.name, reason="Conservative high-confidence setup with strong liquidity.", entry_mode="LIMIT_CONTRACT", exit_mode="TARGET_STOP_TIME_CONTRACT", max_hold_minutes=240, max_loss_fraction=0.08),
        )

