from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engine_contract_builder import EngineContractBuilder
from app.strategy.engines._helpers import capital_allowed, component, hard_blocks, has_candidate


class MakerEngine:
    name = "MAKER"

    def __init__(self) -> None:
        self.contracts = EngineContractBuilder()

    def evaluate(self, payload) -> EngineDecision:
        reasons = hard_blocks(payload)
        orderbook = payload.technical_truth.get("orderbook_signal") or {}
        if not has_candidate(payload, self.name):
            reasons.append("not_suggested_by_opportunity")
        if orderbook.get("has_bid_ask") is False:
            reasons.append("maker_requires_orderbook_truth")
        if float(orderbook.get("depth_2c") or 0) < 250:
            reasons.append("maker_requires_spread_depth")
        if component(payload, "adverse_selection_risk") > 0.35 or component(payload, "trap_risk") > 0.45:
            reasons.append("maker_rejects_adverse_selection")
        if component(payload, "liquidity_quality") < 0.65:
            reasons.append("maker_requires_quality_liquidity")
        if not capital_allowed(payload):
            reasons.append("capital_not_allowed")
        if reasons:
            return EngineDecision(engine=self.name, eligible=False, engine_score=0.0, confidence=component(payload, "confidence"), rejection_reason=reasons[0], severity="BLOCKING" if reasons[0] in hard_blocks(payload) else "WARNING")
        score = min(1.0, component(payload, "liquidity_quality") * 0.35 + component(payload, "fee_reward_advantage") * 0.25 + (1 - component(payload, "adverse_selection_risk")) * 0.2 + payload.opportunity_score * 0.2)
        return EngineDecision(
            engine=self.name,
            eligible=True,
            engine_score=score,
            confidence=component(payload, "confidence"),
            contract=self.contracts.build(payload, engine=self.name, reason="Orderbook and reward capture candidate with maker-first contract terms.", entry_mode="MAKER_ONLY_CONTRACT", exit_mode="CANCEL_REPRICE_TARGET_CONTRACT", max_hold_minutes=360, max_loss_fraction=0.06),
        )

