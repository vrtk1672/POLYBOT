from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import DatabaseConnectionFactory
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.market_memory.contracts import MarketMemory, MarketMemorySnapshot
from app.market_memory.engine_performance_memory_builder import EnginePerformanceMemoryBuilder
from app.market_memory.market_family_memory_builder import MarketFamilyMemoryBuilder
from app.market_memory.market_memory_builder import MarketMemoryBuilder
from app.market_memory.memory_errors import MarketMemoryBlocked
from app.market_memory.no_trade_memory_builder import NoTradeMemoryBuilder
from app.market_memory.rules_risk_memory_builder import RulesRiskMemoryBuilder
from app.market_memory.slippage_memory_builder import SlippageMemoryBuilder
from app.market_memory.source_reliability_memory_builder import SourceReliabilityMemoryBuilder
from app.market_memory.whale_memory_builder import WhaleMemoryBuilder
from app.repositories.engine_performance_memory_repository import EnginePerformanceMemoryRepository
from app.repositories.market_family_memory_repository import MarketFamilyMemoryRepository
from app.repositories.market_memory_repository import MarketMemoryRepository
from app.repositories.no_trade_memory_repository import NoTradeMemoryRepository
from app.repositories.rules_risk_memory_repository import RulesRiskMemoryRepository
from app.repositories.slippage_memory_repository import SlippageMemoryRepository
from app.repositories.source_reliability_memory_repository import SourceReliabilityMemoryRepository
from app.repositories.whale_memory_repository import WhaleMemoryRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor


class MarketMemoryService:
    def __init__(
        self,
        *,
        connection_factory: DatabaseConnectionFactory | None = None,
        event_bus: EventBus | None = None,
        state_governor: StateGovernor | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._event_bus = event_bus or EventBus(connection_factory=self._factory)
        self._governor = state_governor or StateGovernor(connection_factory=self._factory)
        self.market_builder = MarketMemoryBuilder()
        self.family_builder = MarketFamilyMemoryBuilder()
        self.engine_builder = EnginePerformanceMemoryBuilder()
        self.source_builder = SourceReliabilityMemoryBuilder()
        self.whale_builder = WhaleMemoryBuilder()
        self.slippage_builder = SlippageMemoryBuilder()
        self.rules_builder = RulesRiskMemoryBuilder()
        self.no_trade_builder = NoTradeMemoryBuilder()
        self.market_repo = MarketMemoryRepository()
        self.family_repo = MarketFamilyMemoryRepository()
        self.engine_repo = EnginePerformanceMemoryRepository()
        self.source_repo = SourceReliabilityMemoryRepository()
        self.whale_repo = WhaleMemoryRepository()
        self.slippage_repo = SlippageMemoryRepository()
        self.rules_repo = RulesRiskMemoryRepository()
        self.no_trade_repo = NoTradeMemoryRepository()

    def rebuild(self, *, market_id: str | None = None, market_family: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        self._assert_rebuild_allowed()
        if not self._factory.enabled:
            snapshot = MarketMemorySnapshot(market_id=market_id or "UNKNOWN", market_family=market_family, insufficient_data=["database_disabled"])
            return {"dry_run": dry_run, "written": False, "snapshots": [snapshot.model_dump(mode="json")]}
        with self._factory.connect() as conn:
            market_ids = [market_id] if market_id else [row["market_id"] for row in conn.execute("SELECT DISTINCT market_id FROM market_technical_signals ORDER BY market_id LIMIT 200").fetchall()]
            if not market_ids:
                market_ids = [market_id or "UNKNOWN"]
            snapshots: list[MarketMemorySnapshot] = []
            market_memories: list[MarketMemory] = []
            for mid in market_ids:
                tech_rows = self._technical_rows(conn, mid)
                family = market_family or self._infer_family(conn, mid)
                rules_rows = self._rules_rows(conn, mid)
                engine_memory = self.engine_builder.build("UNKNOWN", family or "UNKNOWN", [])
                market_memory = self.market_builder.build(mid, tech_rows, market_family=family, rules_rows=rules_rows, engine_rows=[engine_memory.model_dump()])
                slippage_memory = self.slippage_builder.build(tech_rows, market_id=mid, market_family=family)
                rules_memory = self.rules_builder.build(rules_rows, market_id=mid, market_family=family)
                no_trade_memory = self.no_trade_builder.build([], market_id=mid, market_family=family, reason="insufficient_data")
                whale_rows = self._whale_rows(conn, mid)
                whale_memories = [self.whale_builder.build(row["whale_id"], [row], market_family=family) for row in whale_rows]
                if not whale_memories:
                    whale_memories = [self.whale_builder.build("UNKNOWN", [], market_family=family)]
                source_memories = self._source_memories(conn, family)
                insufficient = []
                if not tech_rows:
                    insufficient.append("missing_v2_8_technical_signals")
                if engine_memory.observations_count == 0:
                    insufficient.append("missing_engine_outcomes")
                if not rules_rows:
                    insufficient.append("missing_rules_history")
                if no_trade_memory.observations_count == 0:
                    insufficient.append("missing_no_trade_regret_history")
                if not whale_rows:
                    insufficient.append("missing_whale_history")
                snapshot = MarketMemorySnapshot(
                    market_id=mid,
                    market_family=family,
                    market_memory=market_memory,
                    engine_memory=[engine_memory],
                    source_memory=source_memories,
                    whale_memory=whale_memories,
                    slippage_memory=[slippage_memory],
                    rules_risk_memory=[rules_memory],
                    no_trade_memory=[no_trade_memory],
                    confidence=market_memory.memory_confidence,
                    insufficient_data=insufficient,
                    updated_at=datetime.now(UTC),
                )
                snapshots.append(snapshot)
                market_memories.append(market_memory)
            family_groups: dict[str, list[MarketMemory]] = {}
            for memory in market_memories:
                family_groups.setdefault(memory.market_family or "UNKNOWN", []).append(memory)
            family_memories = [self.family_builder.build(family, memories) for family, memories in family_groups.items()]
            if dry_run:
                for idx, snapshot in enumerate(snapshots):
                    if snapshot.market_family in family_groups:
                        snapshot.market_family_memory = next((fm for fm in family_memories if fm.market_family == snapshot.market_family), None)
                return {"dry_run": True, "written": False, "snapshots": [snapshot.model_dump(mode="json") for snapshot in snapshots]}
            with conn.transaction():
                for snapshot in snapshots:
                    if snapshot.market_memory:
                        self.market_repo.upsert(conn, snapshot.market_memory)
                    for item in snapshot.engine_memory:
                        self.engine_repo.insert(conn, item)
                    for item in snapshot.source_memory:
                        self.source_repo.insert(conn, item)
                    for item in snapshot.whale_memory:
                        self.whale_repo.insert(conn, item)
                    for item in snapshot.slippage_memory:
                        self.slippage_repo.insert(conn, item)
                    for item in snapshot.rules_risk_memory:
                        self.rules_repo.insert(conn, item)
                    for item in snapshot.no_trade_memory:
                        self.no_trade_repo.insert(conn, item)
                for family_memory in family_memories:
                    self.family_repo.upsert(conn, family_memory)
            conn.commit()
            for snapshot in snapshots:
                self._publish_snapshot(snapshot)
            for family_memory in family_memories:
                self._event_bus.publish(EventType.MARKET_FAMILY_MEMORY_UPDATED.value, {"market_family": family_memory.market_family, "confidence": family_memory.memory_confidence}, "market_memory", aggregate_type="market_family", aggregate_id=family_memory.market_family)
            return {"dry_run": False, "written": True, "snapshots": [snapshot.model_dump(mode="json") for snapshot in snapshots], "families": [item.model_dump(mode="json") for item in family_memories]}

    def health(self) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"status": "DISABLED", "last_update_ts": None, "memories_updated_today": 0, "insufficient_data_count": 0, "errors_today": 0}
        try:
            with self._factory.connect() as conn:
                row = self.market_repo.health(conn)
            return {
                "status": "HEALTHY" if row and row.get("last_update_ts") else "EMPTY",
                "last_update_ts": _iso((row or {}).get("last_update_ts")),
                "memories_updated_today": int((row or {}).get("memories_updated_today") or 0),
                "insufficient_data_count": int((row or {}).get("insufficient_data_count") or 0),
                "errors_today": 0,
            }
        except Exception as exc:
            return {"status": "ERROR", "last_update_ts": None, "memories_updated_today": 0, "insufficient_data_count": 0, "errors_today": 1, "error": str(exc)}

    def market(self, market_id: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"market_id": market_id, "market_memory": None}
        with self._factory.connect() as conn:
            market = self.market_repo.latest_for_market(conn, market_id)
            family = self.family_repo.get(conn, market.get("market_family")) if market and market.get("market_family") else None
            return {"market_id": market_id, "market_memory": _serialize(market), "market_family_memory": _serialize(family), "confidence": float((market or {}).get("memory_confidence") or 0), "insufficient_data": [] if market and market.get("memory_status") != "insufficient_data" else ["insufficient_data"]}

    def family(self, market_family: str) -> dict[str, Any]:
        if not self._factory.enabled:
            return {"market_family": market_family, "market_family_memory": None}
        with self._factory.connect() as conn:
            family = self.family_repo.get(conn, market_family)
            return {"market_family": market_family, "market_family_memory": _serialize(family), "count": 1 if family else 0}

    def list_table(self, table: str, *, limit: int = 100) -> list[dict[str, Any]]:
        if not self._factory.enabled:
            return []
        allowed = {"market_memory_v2", "market_family_memory", "engine_performance_memory", "source_reliability_memory", "whale_memory", "slippage_memory", "rules_risk_memory", "no_trade_memory"}
        if table not in allowed:
            raise ValueError("unsupported memory table")
        with self._factory.connect() as conn:
            return [_serialize(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY updated_at DESC, id DESC LIMIT %s", (limit,)).fetchall()]

    def _assert_rebuild_allowed(self) -> None:
        if not self._factory.enabled:
            return
        try:
            self._governor.assert_can_execute(RuntimeAction.COLLECT_DATA)
        except Exception as exc:
            raise MarketMemoryBlocked("market memory rebuild blocked by runtime mode") from exc

    def _technical_rows(self, conn, market_id: str) -> list[dict[str, Any]]:
        return conn.execute(
            """
            SELECT mts.*, obs.spread_bps, obs.depth_1c, obs.depth_2c, obs.depth_5c,
                   ls.expected_fill_score, ls.expected_slippage_bps, ls.exit_quality_score,
                   ls.liquidity_block_reason, ts.time_efficiency_score
            FROM market_technical_signals mts
            LEFT JOIN LATERAL (
                SELECT * FROM orderbook_signals o WHERE o.market_id = mts.market_id ORDER BY ts DESC, id DESC LIMIT 1
            ) obs ON TRUE
            LEFT JOIN LATERAL (
                SELECT * FROM liquidity_signals l WHERE l.market_id = mts.market_id ORDER BY ts DESC, id DESC LIMIT 1
            ) ls ON TRUE
            LEFT JOIN LATERAL (
                SELECT * FROM time_signals t WHERE t.market_id = mts.market_id ORDER BY ts DESC, id DESC LIMIT 1
            ) ts ON TRUE
            WHERE mts.market_id = %s
            ORDER BY mts.ts DESC, mts.id DESC
            LIMIT 100
            """,
            (market_id,),
        ).fetchall()

    def _rules_rows(self, conn, market_id: str) -> list[dict[str, Any]]:
        if conn.execute("SELECT to_regclass('rules_analysis') AS name").fetchone()["name"] is None:
            return []
        return conn.execute("SELECT * FROM rules_analysis WHERE market_id = %s ORDER BY created_at DESC LIMIT 50", (market_id,)).fetchall()

    def _whale_rows(self, conn, market_id: str) -> list[dict[str, Any]]:
        if conn.execute("SELECT to_regclass('whale_market_scores') AS name").fetchone()["name"] is None:
            return []
        return conn.execute("SELECT whale_id, follow_value, noise_penalty, smart_whale_alignment AS timing_quality FROM whale_market_scores WHERE market_id = %s ORDER BY computed_at DESC NULLS LAST, created_at DESC LIMIT 10", (market_id,)).fetchall()

    def _source_memories(self, conn, market_family: str | None):
        memories = []
        for table, source_type, name_col, strength_col in [
            ("news_impact_scores", "news", "news_event_id", "strength"),
            ("social_hype_scores", "social", "market_id", "hype_pressure"),
            ("whale_market_scores", "whale", "whale_id", "follow_value"),
        ]:
            if conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is None:
                continue
            rows = conn.execute(f"SELECT {name_col} AS source_name, {strength_col} AS signal_strength FROM {table} ORDER BY id DESC LIMIT 25").fetchall()
            if rows:
                observations = [{"supported": None, "latency_seconds": None} for _ in rows]
                memories.append(self.source_builder.build(source_type, source_type, observations, market_family=market_family))
        if not memories:
            memories.append(self.source_builder.build("technical", "v2.8", [], market_family=market_family))
        return memories

    def _infer_family(self, conn, market_id: str) -> str:
        for table, column in (("market_family_map", "market_family"), ("markets_v2", "market_family")):
            if conn.execute("SELECT to_regclass(%s) AS name", (table,)).fetchone()["name"] is None:
                continue
            try:
                row = conn.execute(f"SELECT {column} AS family FROM {table} WHERE market_id = %s LIMIT 1", (market_id,)).fetchone()
                if row and row.get("family"):
                    return str(row["family"])
            except Exception:
                continue
        return "UNKNOWN"

    def _publish_snapshot(self, snapshot: MarketMemorySnapshot) -> None:
        payload = {"market_id": snapshot.market_id, "market_family": snapshot.market_family, "confidence": snapshot.confidence, "insufficient_data": snapshot.insufficient_data}
        self._event_bus.publish(EventType.MARKET_MEMORY_UPDATED.value, payload, "market_memory", aggregate_type="market", aggregate_id=snapshot.market_id)
        if snapshot.insufficient_data:
            self._event_bus.publish(EventType.MARKET_MEMORY_INSUFFICIENT_DATA.value, payload, "market_memory", aggregate_type="market", aggregate_id=snapshot.market_id)
        for event_type, items, key in [
            (EventType.ENGINE_PERFORMANCE_MEMORY_UPDATED.value, snapshot.engine_memory, "engine"),
            (EventType.SOURCE_RELIABILITY_MEMORY_UPDATED.value, snapshot.source_memory, "source_name"),
            (EventType.WHALE_MEMORY_UPDATED.value, snapshot.whale_memory, "whale_id"),
            (EventType.SLIPPAGE_MEMORY_UPDATED.value, snapshot.slippage_memory, "market_id"),
            (EventType.RULES_RISK_MEMORY_UPDATED.value, snapshot.rules_risk_memory, "market_id"),
            (EventType.NO_TRADE_MEMORY_UPDATED.value, snapshot.no_trade_memory, "reason"),
        ]:
            for item in items:
                body = item.model_dump(mode="json")
                self._event_bus.publish(event_type, {"market_id": snapshot.market_id, "ref": body.get(key), "confidence": body.get("confidence", body.get("memory_confidence", 0))}, "market_memory", aggregate_type="market", aggregate_id=snapshot.market_id)


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _serialize(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _iso(value) for key, value in dict(row).items()}
