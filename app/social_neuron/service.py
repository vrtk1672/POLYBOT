from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.social_neuron.ai_context_analyzer import SocialAIContextAnalyzer
from app.social_neuron.bot_spam_filter import BotSpamFilter
from app.social_neuron.collector import SocialCollector
from app.social_neuron.deduplicator import SocialDeduplicator
from app.social_neuron.hype_pressure_scorer import HypePressureScorer
from app.social_neuron.market_linker import SocialMarketLinker
from app.social_neuron.narrative_detector import NarrativeDetector
from app.social_neuron.normalizer import SocialNormalizer
from app.social_neuron.sentiment_classifier import SentimentClassifier
from app.social_neuron.social_errors import SocialCollectionBlocked


class SocialNeuronService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
        ai_analyzer: SocialAIContextAnalyzer | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.collector = SocialCollector(connection_factory=self._factory, event_bus=self._event_bus)
        self.normalizer = SocialNormalizer(connection_factory=self._factory, event_bus=self._event_bus)
        self.deduplicator = SocialDeduplicator(connection_factory=self._factory, event_bus=self._event_bus)
        self.noise_filter = BotSpamFilter(connection_factory=self._factory, event_bus=self._event_bus)
        self.linker = SocialMarketLinker(connection_factory=self._factory, event_bus=self._event_bus)
        self.sentiment = SentimentClassifier(connection_factory=self._factory, event_bus=self._event_bus)
        self.narratives = NarrativeDetector(connection_factory=self._factory, event_bus=self._event_bus)
        self.hype = HypePressureScorer(connection_factory=self._factory, event_bus=self._event_bus)
        self.ai_analyzer = ai_analyzer or SocialAIContextAnalyzer(connection_factory=self._factory, event_bus=self._event_bus)

    def collect_and_process_sources(self, *, source_id: str | None = None, limit_per_source: int = 10, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_events = self.collector.collect_from_source(source_id, limit=limit_per_source) if source_id else self.collector.collect_all_enabled(limit_per_source=limit_per_source)
        items = [self.process_raw_event(event, analyze_with_ai=analyze_with_ai) for event in raw_events]
        return {
            "raw_events": len(raw_events),
            "normalized_events": sum(1 for item in items if item.get("normalized_event_id")),
            "market_links": sum(int(item.get("link_count") or 0) for item in items),
            "hype_scores": sum(int(item.get("hype_count") or 0) for item in items),
            "items": items,
        }

    def process_manual_social(self, payload: dict[str, Any], *, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_event, created = self.collector.collect_manual(payload)
        summary = self.process_raw_event(raw_event, analyze_with_ai=analyze_with_ai)
        summary["raw_created"] = created
        return summary

    def process_raw_event(self, raw_event: Any, *, analyze_with_ai: bool = False) -> dict[str, Any]:
        normalized = self.normalizer.normalize_raw_event(raw_event)
        self.normalizer.persist_normalized_event(normalized)
        group_id = self.deduplicator.deduplicate(normalized)
        normalized.dedup_group_id = group_id
        noise = self.noise_filter.compute_noise_score(normalized)
        normalized.spam_score = noise.spam_score
        normalized.bot_risk = noise.bot_risk
        self.normalizer.persist_normalized_event(normalized)
        self.noise_filter.persist_noise_score(noise)
        links = self.linker.link_social_to_markets(normalized)
        narrative = self.narratives.update_narrative(normalized, links)
        sentiment_scores = []
        hype_scores = []
        analyses = []
        for link in links:
            score = self.sentiment.classify(normalized, link)
            self.sentiment.persist_score(score)
            sentiment_scores.append(score)
            market_noise = self.noise_filter.compute_noise_score(normalized, market_id=link.market_id)
            self.noise_filter.persist_noise_score(market_noise)
            hype = self.hype.score_hype_pressure(link.market_id, sentiment_score=score, narrative=narrative)
            self.hype.persist_hype_score(hype)
            hype_scores.append(hype)
            if analyze_with_ai:
                analyses.append(self.ai_analyzer.analyze_social_context(normalized, link, hype, allow_cloud=False))
        return {
            "raw_social_event_id": normalized.raw_social_event_id,
            "normalized_event_id": normalized.social_event_id,
            "dedup_group_id": group_id,
            "noise_score": noise.noise_score,
            "link_count": len(links),
            "sentiment_count": len(sentiment_scores),
            "hype_count": len(hype_scores),
            "narrative_id": narrative.narrative_id,
            "ai_analysis_count": len(analyses),
            "links": [link.model_dump(mode="json") for link in links],
            "hype_scores": [score.model_dump(mode="json") for score in hype_scores],
        }

    def _assert_collection_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.COLLECT_DATA)
        except Exception as exc:
            raise SocialCollectionBlocked("social collection blocked by runtime mode") from exc
