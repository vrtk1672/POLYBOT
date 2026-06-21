from __future__ import annotations

from typing import Any

from app.market_memory.contracts import WhaleMemory, avg, bounded


class WhaleMemoryBuilder:
    def build(self, whale_id: str, rows: list[dict[str, Any]], *, market_family: str | None = None) -> WhaleMemory:
        observations = len(rows)
        follow_value = avg([row.get("follow_value") for row in rows]) or 0
        noise = avg([row.get("noise_score") or row.get("noise_penalty") for row in rows]) if rows else 0.5
        timing = avg([row.get("timing_quality") for row in rows])
        size = avg([row.get("average_trade_size_usd") or row.get("size_usd") for row in rows])
        score = bounded((follow_value * 0.45) + ((1 - (noise or 0.5)) * 0.35) + ((timing or 0) * 0.2))
        confidence = bounded(observations / 20)
        return WhaleMemory(
            whale_id=whale_id,
            market_family=market_family,
            observations_count=observations,
            follow_value_avg=follow_value,
            noise_score_avg=noise or 0.5,
            avg_timing_quality=timing,
            avg_size_usd=size,
            whale_score=score if observations else 0.0,
            confidence=confidence,
            summary={"source": "v2.9", "size_alone_is_not_intelligence": True},
        )

