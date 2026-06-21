from __future__ import annotations

from app.market_memory.contracts import MarketFamilyMemory, MarketMemory, avg, bounded


class MarketFamilyMemoryBuilder:
    def build(self, market_family: str, memories: list[MarketMemory]) -> MarketFamilyMemory:
        observations = sum(memory.observations_count for memory in memories)
        engines = [memory.best_engine for memory in memories if memory.best_engine != "UNKNOWN"]
        best_engine = max(set(engines), key=engines.count) if engines else "UNKNOWN"
        return MarketFamilyMemory(
            market_family=market_family,
            observations_count=observations,
            markets_count=len({memory.market_id for memory in memories}),
            best_engine=best_engine,
            avg_spread_bps=avg([memory.avg_spread_bps for memory in memories]),
            avg_depth_2c=avg([memory.avg_depth_2c for memory in memories]),
            avg_slippage_bps=avg([memory.avg_slippage_bps for memory in memories]),
            technical_block_rate=avg([memory.technical_block_rate for memory in memories]) or 0,
            memory_confidence=bounded(avg([memory.memory_confidence for memory in memories]) or 0),
            summary={"source": "v2.9", "evidence_markets": len(memories)},
        )

