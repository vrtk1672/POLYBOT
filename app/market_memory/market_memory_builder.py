from __future__ import annotations

from typing import Any

from app.market_memory.contracts import MarketMemory, avg, bounded


class MarketMemoryBuilder:
    def build(self, market_id: str, technical_rows: list[dict[str, Any]], *, market_family: str | None = None, rules_rows: list[dict[str, Any]] | None = None, engine_rows: list[dict[str, Any]] | None = None) -> MarketMemory:
        rows = technical_rows or []
        rules_rows = rules_rows or []
        observations = len(rows)
        best_engine = "UNKNOWN"
        best_confidence = 0.0
        if engine_rows:
            ranked = sorted(engine_rows, key=lambda row: float(row.get("engine_score") or 0), reverse=True)
            if ranked and int(ranked[0].get("observations_count") or 0) > 0:
                best_engine = str(ranked[0].get("engine") or "UNKNOWN")
                best_confidence = bounded(ranked[0].get("confidence"))
        confidence = bounded(min(observations / 10, 1) * 0.7 + best_confidence * 0.3)
        return MarketMemory(
            market_id=market_id,
            market_family=market_family,
            observations_count=observations,
            best_engine=best_engine,
            avg_price=avg([r.get("price_yes") for r in rows]),
            avg_spread_bps=avg([r.get("spread_bps") for r in rows]),
            avg_depth_1c=avg([r.get("depth_1c") for r in rows]),
            avg_depth_2c=avg([r.get("depth_2c") for r in rows]),
            avg_depth_5c=avg([r.get("depth_5c") for r in rows]),
            avg_fill_rate=avg([r.get("expected_fill_score") for r in rows]),
            avg_slippage_bps=avg([r.get("expected_slippage_bps") for r in rows]),
            avg_exit_quality=avg([r.get("exit_quality_score") for r in rows]),
            avg_time_efficiency=avg([r.get("time_efficiency_score") for r in rows]),
            wording_risk_avg=avg([r.get("wording_risk") for r in rules_rows]),
            dispute_risk_avg=avg([r.get("dispute_risk") for r in rules_rows]),
            technical_block_rate=_rate([r.get("technical_blocked") for r in rows]),
            liquidity_failure_rate=_rate([r.get("liquidity_block_reason") for r in rows]),
            stale_data_rate=_rate([r.get("stale") for r in rows]),
            memory_confidence=confidence,
            summary={"source": "v2.9", "best_engine_evidence": best_confidence, "insufficient_data": observations == 0},
        )


def _rate(values: list[Any]) -> float:
    if not values:
        return 0.0
    return bounded(sum(1 for value in values if bool(value)) / len(values))

