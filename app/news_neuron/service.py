from __future__ import annotations

from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.news_neuron.ai_context_analyzer import NewsAIContextAnalyzer
from app.news_neuron.collector import NewsCollector
from app.news_neuron.deduplicator import NewsDeduplicator
from app.news_neuron.impact_scorer import NewsImpactScorer
from app.news_neuron.market_linker import NewsMarketLinker
from app.news_neuron.news_errors import NewsCollectionBlocked
from app.news_neuron.normalizer import NewsNormalizer
from app.news_neuron.source_reliability import SourceReliabilityScorer
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class NewsNeuronService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
        ai_analyzer: NewsAIContextAnalyzer | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.collector = NewsCollector(connection_factory=self._factory, event_bus=self._event_bus)
        self.normalizer = NewsNormalizer(connection_factory=self._factory, event_bus=self._event_bus)
        self.deduplicator = NewsDeduplicator(connection_factory=self._factory, event_bus=self._event_bus)
        self.linker = NewsMarketLinker(connection_factory=self._factory, event_bus=self._event_bus)
        self.impact_scorer = NewsImpactScorer(connection_factory=self._factory, event_bus=self._event_bus)
        self.reliability = SourceReliabilityScorer(connection_factory=self._factory, event_bus=self._event_bus)
        self.ai_analyzer = ai_analyzer or NewsAIContextAnalyzer(connection_factory=self._factory, event_bus=self._event_bus)

    def collect_and_process_sources(self, *, source_id: str | None = None, limit_per_source: int = 10, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_events = self.collector.collect_from_source(source_id, limit=limit_per_source) if source_id else self.collector.collect_all_enabled(limit_per_source=limit_per_source)
        summaries = [self.process_raw_event(event, analyze_with_ai=analyze_with_ai) for event in raw_events]
        return {
            "raw_events": len(raw_events),
            "normalized_events": sum(1 for item in summaries if item.get("normalized_event_id")),
            "market_links": sum(int(item.get("link_count") or 0) for item in summaries),
            "impact_scores": sum(int(item.get("impact_count") or 0) for item in summaries),
            "items": summaries,
        }

    def process_manual_news(self, payload: dict[str, Any], *, analyze_with_ai: bool = False) -> dict[str, Any]:
        self._assert_collection_allowed()
        raw_event, created = self.collector.collect_manual(payload)
        summary = self.process_raw_event(raw_event, analyze_with_ai=analyze_with_ai)
        summary["raw_created"] = created
        return summary

    def process_raw_event(self, raw_event: Any, *, analyze_with_ai: bool = False) -> dict[str, Any]:
        normalized = self.normalizer.normalize_raw_event(raw_event)
        self.normalizer.persist_normalized_event(normalized)
        group = self.deduplicator.deduplicate(normalized)
        links = self.linker.link_news_to_markets(normalized)
        impacts = []
        analyses = []
        for link in links:
            impact = self.impact_scorer.score_news_impact(normalized, link)
            self.impact_scorer.persist_impact_score(impact)
            impacts.append(impact)
            if analyze_with_ai:
                analyses.append(self.ai_analyzer.analyze_news_context(normalized, link, impact, allow_cloud=False))
        self.reliability.update_source_reliability(normalized.source_id)
        return {
            "raw_event_id": normalized.raw_event_id,
            "normalized_event_id": normalized.news_event_id,
            "dedup_group_id": group.dedup_group_id,
            "link_count": len(links),
            "impact_count": len(impacts),
            "ai_analysis_count": len(analyses),
            "links": [link.model_dump(mode="json") for link in links],
            "impacts": [impact.model_dump(mode="json") for impact in impacts],
        }

    def _assert_collection_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.COLLECT_DATA)
        except Exception as exc:
            raise NewsCollectionBlocked("news collection blocked by runtime mode") from exc

