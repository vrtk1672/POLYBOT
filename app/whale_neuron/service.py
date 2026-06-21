from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.whale_neuron.ai_context_analyzer import WhaleAIContextAnalyzer
from app.whale_neuron.category_engine import WhaleCategoryEngine
from app.whale_neuron.event_classifier import WhaleEventClassifier
from app.whale_neuron.follow_value import WhaleFollowValueScorer
from app.whale_neuron.market_score import WhaleMarketScorer
from app.whale_neuron.normalizer import WhaleEventNormalizer
from app.whale_neuron.profile_builder import WhaleProfileBuilder
from app.whale_neuron.registry import WhaleRegistry
from app.whale_neuron.scanner import WhaleScanner
from app.whale_neuron.source_registry import WhaleSourceRegistry
from app.whale_neuron.whale_errors import WhaleCollectionBlocked


class WhaleNeuronService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
        ai_analyzer: WhaleAIContextAnalyzer | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.sources = WhaleSourceRegistry(connection_factory=self._factory, event_bus=self._event_bus)
        self.scanner = WhaleScanner(connection_factory=self._factory, event_bus=self._event_bus)
        self.normalizer = WhaleEventNormalizer(connection_factory=self._factory, event_bus=self._event_bus)
        self.registry = WhaleRegistry(connection_factory=self._factory, event_bus=self._event_bus)
        self.classifier = WhaleEventClassifier()
        self.profiles = WhaleProfileBuilder(connection_factory=self._factory, event_bus=self._event_bus)
        self.categories = WhaleCategoryEngine(connection_factory=self._factory, event_bus=self._event_bus)
        self.market_scores = WhaleMarketScorer(connection_factory=self._factory, event_bus=self._event_bus)
        self.follow = WhaleFollowValueScorer(connection_factory=self._factory, event_bus=self._event_bus)
        self.ai_analyzer = ai_analyzer or WhaleAIContextAnalyzer(connection_factory=self._factory, event_bus=self._event_bus)

    def scan_and_process_sources(self, *, source_id: str | None = None, limit_per_source: int = 10, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_events = self.scanner.scan_source(source_id, limit_per_source) if source_id else self.scanner.scan_all_enabled(limit_per_source)
        items = [self.process_raw_event(event, analyze_with_ai=analyze_with_ai) for event in raw_events]
        return {"raw_events": len(raw_events), "processed": len(items), "items": items}

    def process_manual_whale_event(self, payload: dict[str, Any], *, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_event = self.scanner.ingest_manual_event(payload)
        return self.process_raw_event(raw_event, analyze_with_ai=analyze_with_ai)

    def process_raw_event(self, raw_event: dict[str, Any], *, analyze_with_ai: bool = False) -> dict[str, Any]:
        event = self.normalizer.normalize_raw_event(raw_event)
        classification, confidence = self.classifier.classify_event(event)
        event.event_classification = classification
        event.confidence = max(event.confidence, confidence)
        row, created = self.normalizer.persist_whale_event(event)
        whale = self.registry.upsert_whale(event)
        profile = self.profiles.rebuild_whale_profile(event.whale_id or "unknown")
        categories = self.categories.assign_categories(profile)
        market_score = self.market_scores.score_whale_for_market(event, profile)
        if market_score:
            self.market_scores.persist_market_score(market_score)
        decision = self.follow.compute_follow_value(profile, event, market_score)
        self.follow.persist_follow_decision(decision)
        ai = self.ai_analyzer.analyze_whale_context(event, profile, market_score, allow_cloud=False) if analyze_with_ai else None
        return {
            "whale_event_id": event.whale_event_id,
            "event_created": created,
            "whale_id": event.whale_id,
            "whale_registered": bool(whale),
            "event_classification": event.event_classification.value,
            "profile": profile.model_dump(mode="json"),
            "categories": [category.model_dump(mode="json") for category in categories],
            "market_score": market_score.model_dump(mode="json") if market_score else None,
            "follow_decision": decision.model_dump(mode="json"),
            "ai_analysis": ai,
            "row_id": row.get("id") if isinstance(row, dict) else None,
        }

    def _assert_collection_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.COLLECT_DATA)
        except Exception as exc:
            raise WhaleCollectionBlocked("whale scanning blocked by runtime mode") from exc

