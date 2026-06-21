from __future__ import annotations

from app.learning.contracts import MemoryUpdateDecision


class MemoryUpdateCoordinator:
    def evaluate(self, *, confidence: float, evidence_exists: bool, requested: bool = True) -> MemoryUpdateDecision:
        if not requested:
            return MemoryUpdateDecision(allowed=False, update_memory=False, confidence=confidence, reason="memory_update_not_requested")
        if not evidence_exists:
            return MemoryUpdateDecision(allowed=False, update_memory=False, confidence=confidence, reason="missing_evidence")
        if confidence < 0.7:
            return MemoryUpdateDecision(allowed=False, update_memory=False, confidence=confidence, reason="confidence_below_memory_threshold")
        return MemoryUpdateDecision(allowed=True, update_memory=True, confidence=confidence, reason="confidence_and_evidence_sufficient")
