from __future__ import annotations

from app.news_neuron.contracts import NormalizedNewsEvent
from app.news_neuron.deduplicator import NewsDeduplicator


def _event(title: str, event_id: str = "n1") -> NormalizedNewsEvent:
    return NormalizedNewsEvent(news_event_id=event_id, source_id="manual", title=title, normalized_title=title.lower(), topics=["crypto"], entities=["BTC"])


def test_same_story_hashes_to_same_group_signature() -> None:
    dedup = NewsDeduplicator()
    first = _event("BTC breaks above key level", "n1")
    second = _event("BTC breaks above key level", "n2")
    assert dedup.compute_group_hash(first) == dedup.compute_group_hash(second)


def test_different_story_not_deduped_by_hash() -> None:
    dedup = NewsDeduplicator()
    assert dedup.compute_group_hash(_event("BTC breaks above key level")) != dedup.compute_group_hash(_event("Election court ruling", "n2"))

