from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class HuntEngine:
    name = "HUNT"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if not payload.hunt_approval:
            reasons.append("hunt_requires_governor_approval")
        if component(payload, "time_efficiency") < 0.7 or component(payload, "trigger_strength") < 0.7:
            reasons.append("hunt_requires_chaos_and_urgency")
        if component(payload, "repricing_potential") < 0.7:
            reasons.append("hunt_requires_high_repricing_potential")
        if component(payload, "exit_probability") < 0.55:
            reasons.append("hunt_requires_strict_exit_viability")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING")
        score = min(1.0, component(payload, "trigger_strength") * 0.3 + component(payload, "time_efficiency") * 0.25 + component(payload, "repricing_potential") * 0.25 + payload.opportunity_score * 0.2)
        return EngineDecision(
            engine=self.name,
            eligible=True,
            engine_score=score,
            confidence=min(component(payload, "confidence"), 0.75),
            contract=self.contracts.build(payload, engine=self.name, reason="Approved high-urgency chaos setup with strict contract-only limits.", entry_mode="STRICT_LIMIT_CONTRACT", exit_mode="FORCED_FAST_EXIT_CONTRACT", max_hold_minutes=30, max_loss_fraction=0.05),
        )

