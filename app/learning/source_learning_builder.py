from __future__ import annotations

from typing import Any

from app.learning.contracts import SourceLearning


class SourceLearningBuilder:
    def build(self, payload: dict[str, Any]) -> SourceLearning:
        usefulness = float(payload.get("usefulness_score") or payload.get("accuracy_score") or 0)
        stale = bool(payload.get("stale") or payload.get("false_signal"))
        confidence = float(payload.get("confidence") or 0.75)
        if confidence < 0.5:
            signal = "insufficient_data"
            delta = 0.0
            result = "INSUFFICIENT_DATA"
        elif stale or usefulness < 0.45:
            signal = "penalize_source"
            delta = -0.05
            result = "MISS"
        else:
            signal = "reward_source"
            delta = 0.04
            result = "HIT"
        prior = payload.get("prior_reliability")
        new_reliability = None if prior is None else max(0.0, min(1.0, float(prior) + delta))
        return SourceLearning(
            source_type=str(payload.get("source_type") or "unknown"),
            source_name=payload.get("source_name"),
            source_id=payload.get("source_id"),
            market_family=payload.get("market_family"),
            observation_type=str(payload.get("observation_type") or "outcome_review"),
            result=result,
            prior_reliability=prior,
            new_reliability=new_reliability,
            usefulness_delta=delta,
            latency_delta=payload.get("latency_delta"),
            confidence=confidence,
            learning_signal=signal,
            explanation="Source learning is evidence-based and recommendation-only.",
        )
