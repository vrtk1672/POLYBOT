from __future__ import annotations

from typing import Any

from app.market_memory.contracts import NoTradeMemory, avg, bounded


class NoTradeMemoryBuilder:
    def build(self, rows: list[dict[str, Any]], *, market_id: str | None = None, market_family: str | None = None, candidate_engine: str | None = None, reason: str = "insufficient_data") -> NoTradeMemory:
        observations = len(rows)
        regret = sum(1 for row in rows if row.get("regret") is True)
        regret_rate = regret / observations if observations else 0.0
        quality = bounded(1 - regret_rate) if observations else 0.0
        reasons = [str(row.get("reason") or row.get("block_reason") or reason) for row in rows] or [reason]
        common = max(set(reasons), key=reasons.count)
        return NoTradeMemory(
            market_id=market_id,
            market_family=market_family,
            candidate_engine=candidate_engine,
            reason=common,
            observations_count=observations,
            regret_rate=regret_rate,
            avg_would_have_roi=avg([row.get("would_have_roi") for row in rows]),
            no_trade_quality_score=quality,
            confidence=bounded(observations / 20),
            summary={"source": "v2.9", "regret_requires_post_fact_evidence": True, "insufficient_data": observations == 0},
        )

