from __future__ import annotations

from typing import Any

from app.market_memory.contracts import EnginePerformanceMemory, avg, bounded


class EnginePerformanceMemoryBuilder:
    def build(self, engine: str, market_family: str, outcomes: list[dict[str, Any]]) -> EnginePerformanceMemory:
        observations = len(outcomes)
        wins = sum(1 for row in outcomes if str(row.get("outcome") or "").upper() in {"WIN", "PROFIT", "GOOD"})
        losses = sum(1 for row in outcomes if str(row.get("outcome") or "").upper() in {"LOSS", "BAD", "FAILED"})
        neutral = max(0, observations - wins - losses)
        win_rate = wins / observations if observations else 0.0
        failed = losses / observations if observations else 0.0
        adverse_selection_rate = sum(1 for row in outcomes if row.get("adverse_selection") is True) / observations if observations else 0.0
        score = bounded((win_rate * 0.65) + (bounded(avg([row.get("roi") for row in outcomes]) or 0) * 0.2) + ((1 - failed) * 0.15))
        confidence = bounded(observations / 20)
        return EnginePerformanceMemory(
            engine=engine,
            market_family=market_family,
            observations_count=observations,
            wins_count=wins,
            losses_count=losses,
            neutral_count=neutral,
            win_rate=win_rate,
            avg_roi=avg([row.get("roi") for row in outcomes]),
            avg_roi_per_hour=avg([row.get("roi_per_hour") for row in outcomes]),
            avg_hold_seconds=avg([row.get("hold_seconds") for row in outcomes]),
            adverse_selection_rate=adverse_selection_rate,
            engine_score=score if observations else 0.0,
            confidence=confidence,
            summary={"source": "v2.9", "insufficient_data": observations == 0},
        )
