from __future__ import annotations

from typing import Any

from app.learning.contracts import AILearning


class AILearningBuilder:
    def build(self, payload: dict[str, Any]) -> AILearning:
        accuracy = float(payload.get("accuracy_score") or (1.0 if payload.get("useful") else 0.0))
        usefulness = float(payload.get("usefulness_score") or accuracy)
        cost = payload.get("cost_usd")
        cost_efficiency = None
        if cost is not None:
            cost_efficiency = usefulness / max(float(cost), 0.01)
        confidence = float(payload.get("confidence") or 0.75)
        signal = "reward_ai" if usefulness >= 0.65 and accuracy >= 0.6 else "penalize_ai" if accuracy < 0.45 else "keep_ai"
        return AILearning(
            ai_request_id=payload.get("ai_request_id"),
            model_name=payload.get("model_name"),
            prompt_version=payload.get("prompt_version"),
            market_id=payload.get("market_id"),
            market_family=payload.get("market_family"),
            task_type=str(payload.get("task_type") or "market_review"),
            predicted_output=payload.get("predicted_output"),
            observed_outcome=payload.get("observed_outcome"),
            usefulness_score=usefulness,
            accuracy_score=accuracy,
            cost_usd=cost,
            cost_efficiency_score=cost_efficiency,
            prior_model_score=payload.get("prior_model_score"),
            new_model_score=None if payload.get("prior_model_score") is None else max(0.0, min(1.0, float(payload["prior_model_score"]) + (0.03 if signal == "reward_ai" else -0.04 if signal == "penalize_ai" else 0.0))),
            confidence=confidence,
            learning_signal=signal,
            explanation="AI learning is scored from observed usefulness, accuracy, and cost efficiency.",
        )
