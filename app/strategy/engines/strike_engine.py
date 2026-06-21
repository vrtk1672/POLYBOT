from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class StrikeEngine:
    name = "STRIKE"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if component(payload, "trigger_strength") < 0.65 or not payload.context_output.get("context_shift", True):
            reasons.append("strike_requires_trigger")
        if component(payload, "repricing_potential") < 0.55:
            reasons.append("strike_requires_repricing_potential")
        if component(payload, "already_priced_in_score") > 0.55:
            reasons.append("strike_rejects_already_priced_in")
        if component(payload, "exit_probability") < 0.55:
            reasons.append("strike_requires_decent_exit_quality")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING" if reasons[0] in hard_blocks(payload) else "WARNING")
        score = min(1.0, component(payload, "trigger_strength") * 0.35 + component(payload, "repricing_potential") * 0.3 + payload.opportunity_score * 0.25 + component(payload, "time_efficiency") * 0.1)
        return EngineDecision(
            engine=self.name,
            eligible=True,
            engine_score=score,
            confidence=component(payload, "confidence"),
            contract=self.contracts.build(payload, engine=self.name, reason="Fast repricing setup with validated trigger and bounded hold time.", entry_mode="LIMIT_OR_CANCEL_CONTRACT", exit_mode="FAST_TARGET_STOP_TIME_CONTRACT", max_hold_minutes=90, max_loss_fraction=0.12),
        )

