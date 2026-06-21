from __future__ import annotations

from app.whale_neuron.contracts import WhaleEventClassification, WhaleProfile, bounded


class WhaleNoisePenalty:
    def compute_noise_score(self, profile: WhaleProfile, events: list[object] | None = None) -> float:
        events = events or []
        late = sum(1 for event in events if getattr(event, "event_classification", None) == WhaleEventClassification.LATE_CHASE)
        churn = self.compute_churn_score(events)
        inconsistency = self.compute_inconsistency_penalty(profile)
        return bounded(max(profile.noise_score, 0.25 * late, churn, inconsistency))

    def compute_churn_score(self, events: list[object]) -> float:
        if len(events) < 4:
            return 0.1
        actions = [str(getattr(event, "action_type", "")) for event in events]
        flips = sum(1 for left, right in zip(actions, actions[1:]) if left != right)
        return bounded(flips / max(1, len(actions) - 1))

    def compute_late_chase_penalty(self, events: list[object]) -> float:
        if not events:
            return 0.0
        late = sum(1 for event in events if getattr(event, "event_classification", None) == WhaleEventClassification.LATE_CHASE)
        return bounded(late / len(events))

    def compute_inconsistency_penalty(self, profile: WhaleProfile) -> float:
        return bounded(1.0 - profile.win_consistency) if profile.win_consistency is not None else 0.35 if profile.sample_size < 3 else 0.2

    def compute_market_family_noise(self, profile: WhaleProfile) -> float:
        return 0.15 if len(profile.market_specialties) <= 3 else bounded((len(profile.market_specialties) - 3) / 10)

    def apply_noise_penalty_to_score(self, score: float, noise_score: float) -> float:
        return bounded(score * (1.0 - 0.7 * bounded(noise_score)))

