from __future__ import annotations

from typing import Any

from app.market_memory.contracts import SourceReliabilityMemory, avg, bounded


class SourceReliabilityMemoryBuilder:
    def build(self, source_type: str, source_name: str, observations: list[dict[str, Any]], *, source_id: str | None = None, market_family: str | None = None) -> SourceReliabilityMemory:
        count = len(observations)
        true_positive = sum(1 for row in observations if row.get("supported") is True)
        false_positive = sum(1 for row in observations if row.get("supported") is False)
        stale = sum(1 for row in observations if row.get("stale") is True)
        duplicate = sum(1 for row in observations if row.get("duplicate") is True)
        reliability = bounded((0.5 + true_positive * 0.08 - false_positive * 0.12 - stale * 0.04 - duplicate * 0.03) if count else 0.5, 0.5)
        usefulness = bounded((true_positive / count) if count else 0.0)
        return SourceReliabilityMemory(
            source_type=source_type,
            source_name=source_name,
            source_id=source_id,
            market_family=market_family,
            observations_count=count,
            true_positive_count=true_positive,
            false_positive_count=false_positive,
            avg_latency_seconds=avg([row.get("latency_seconds") for row in observations]),
            reliability_score=reliability,
            usefulness_score=usefulness,
            confidence=bounded(count / 20),
            summary={"stale_count": stale, "duplicate_count": duplicate, "source": "v2.9"},
        )

