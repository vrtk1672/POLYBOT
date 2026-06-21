from __future__ import annotations

from app.strategy.contracts import EngineDecision
from app.strategy.engines._helpers import component


class ReinvestEngine:
    name = "REINVEST"

    def evaluate(self, payload) -> EngineDecision:
        return EngineDecision(
            engine=self.name,
            eligible=False,
            engine_score=0.0,
            confidence=component(payload, "confidence"),
            rejection_reason="reinvest_requires_v2_13_profit_pocket",
            severity="WARNING",
        )

