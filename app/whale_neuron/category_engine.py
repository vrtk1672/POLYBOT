from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.repositories.whale_category_repository import WhaleCategoryRepository
from app.whale_neuron.contracts import WhaleCategory, WhaleProfile, bounded
from app.whale_neuron.redaction import redact_dict


class WhaleCategoryEngine:
    def __init__(self, *, connection_factory: DatabaseConnectionFactory | None = None, event_bus: EventBus | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._repo = WhaleCategoryRepository()

    def assign_categories(self, whale_profile: WhaleProfile) -> list[WhaleCategory]:
        categories = self.compute_category_scores(whale_profile)
        for category in categories:
            self.persist_category(category)
        return categories

    def compute_category_scores(self, profile: WhaleProfile) -> list[WhaleCategory]:
        if profile.sample_size < 3:
            return [WhaleCategory(whale_id=profile.whale_id, category="unknown", score=0.5, confidence=0.4, reason="insufficient sample")]
        output: list[WhaleCategory] = []
        if profile.timing_quality >= 0.7 and (profile.hit_rate or 0) >= 0.6 and profile.noise_score <= 0.4:
            output.append(WhaleCategory(whale_id=profile.whale_id, category="smart_whale", score=profile.timing_quality, confidence=profile.confidence, reason="good timing and hit proxy"))
        if profile.noise_score >= 0.65:
            output.append(WhaleCategory(whale_id=profile.whale_id, category="noisy_whale", score=profile.noise_score, confidence=profile.confidence, reason="high noise score"))
        if profile.copy_worthy_score >= 0.6:
            output.append(WhaleCategory(whale_id=profile.whale_id, category="copy_worthy_whale", score=profile.copy_worthy_score, confidence=profile.confidence, reason="high follow value with low noise"))
        if profile.momentum_chase_score >= 0.5:
            output.append(WhaleCategory(whale_id=profile.whale_id, category="late_chaser", score=profile.momentum_chase_score, confidence=profile.confidence, reason="repeated late chase behavior"))
        for family in profile.market_specialties:
            if family in {"sports", "politics"}:
                output.append(WhaleCategory(whale_id=profile.whale_id, category=f"{family}_specialist", score=0.7, confidence=bounded(profile.confidence), reason=f"repeated {family} markets"))
        return output or [WhaleCategory(whale_id=profile.whale_id, category="unknown", score=0.4, confidence=profile.confidence, reason="no dominant category")]

    def persist_category(self, category: WhaleCategory) -> dict[str, object]:
        if not self._factory.enabled:
            return category.model_dump(mode="json")
        with self._factory.connect() as conn, conn.transaction():
            row = self._repo.insert_category(conn, category)
        self._event_bus.publish(EventType.WHALE_CATEGORY_ASSIGNED.value, redact_dict(category.model_dump(mode="json")), "whale_neuron", aggregate_type="whale", aggregate_id=category.whale_id)
        return row

