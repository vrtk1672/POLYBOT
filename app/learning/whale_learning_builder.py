from __future__ import annotations

from typing import Any

from app.learning.contracts import WhaleLearning


class WhaleLearningBuilder:
    def build(self, payload: dict[str, Any]) -> WhaleLearning:
        confidence = float(payload.get("confidence") or 0.75)
        noisy = bool(payload.get("noisy") or payload.get("false_positive"))
        hit = bool(payload.get("hit") or payload.get("profitable_follow"))
        follow_delta = 0.04 if hit and not noisy else -0.06 if noisy else 0.0
        noise_delta = -0.03 if hit and not noisy else 0.06 if noisy else 0.0
        prior_follow = payload.get("prior_follow_value")
        prior_noise = payload.get("prior_noise_score")
        return WhaleLearning(
            whale_id=str(payload.get("whale_id") or "unknown_whale"),
            market_family=payload.get("market_family"),
            market_id=payload.get("market_id"),
            observation_type=str(payload.get("observation_type") or "outcome_review"),
            result="HIT" if hit else "NOISY" if noisy else "NEUTRAL",
            prior_follow_value=prior_follow,
            new_follow_value=None if prior_follow is None else max(0.0, min(1.0, float(prior_follow) + follow_delta)),
            prior_noise_score=prior_noise,
            new_noise_score=None if prior_noise is None else max(0.0, min(1.0, float(prior_noise) + noise_delta)),
            hit_rate_delta=follow_delta,
            timing_quality_delta=payload.get("timing_quality_delta"),
            confidence=confidence,
            learning_signal="reward_whale" if hit and not noisy else "penalize_whale" if noisy else "keep_whale",
            explanation="Whale learning uses outcome evidence; size alone is not treated as intelligence.",
        )
