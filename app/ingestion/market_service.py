import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter

from app.config import Settings
from app.data_foundation.service import DataFoundationService
from app.db.config import get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.market_snapshot import MarketSnapshotContract
from app.domain.contracts.ranking_snapshot import RankingSnapshotContract
from app.events.event_bus import EventBus
from app.events.types import EventType
from app.logging import get_logger
from app.models.market import NormalizedMarket
from app.models.score import ScoredMarket
from app.runtime.cycle_orchestrator import RuntimeCycleOrchestrator
from app.runtime.modes import RuntimeAction
from app.runtime.runtime_errors import RuntimePermissionDenied
from app.runtime.service_registry import ServiceRegistry
from app.scoring.opportunity_score import OpportunityScorer
from app.services.runtime_intelligence import RuntimeIntelligenceService
from app.services.runtime_paper_trading import RuntimePaperTradingService
from app.services.recorders.cycle_recorder import CycleRecorder
from app.services.recorders.market_snapshot_recorder import MarketSnapshotRecorder
from app.services.recorders.ranking_snapshot_recorder import RankingSnapshotRecorder
from app.services.brain_mesh_activation import BrainMeshActivationService
from app.services.brain_dialogue import BrainDialogueService
from app.services.downstream_evidence_recompute import DownstreamEvidenceRecomputeService
from app.services.evidence_refresh import EvidenceRefreshService
from app.services.neuron_intelligence import NeuronIntelligenceService
from app.neural_bus.service import NeuralEventBusService
from app.services.candidate_eligibility_recovery import CandidateEligibilityRecoveryService
from app.services.paper_execution import PaperExecutionService
from app.services.paper_exit_loop import PaperExitLoopService
from app.services.paper_intents import PaperIntentGateService
from app.services.post_side_risk_exit_readiness import PostSideRiskExitReadinessService
from app.services.side_evidence import DeterministicSideEvidenceService
from app.services.trusted_orderbook import TrustedOrderbookEvidenceService
from app.utils.terminal import render_top_markets_table
from app.utils.time_utils import parse_datetime

logger = get_logger(__name__)


class MarketService:
    def __init__(
        self,
        settings: Settings,
        gamma_client,
        runtime_intelligence: RuntimeIntelligenceService | None = None,
        brain_mesh_activation: BrainMeshActivationService | None = None,
        brain_dialogue: BrainDialogueService | None = None,
        evidence_refresh: EvidenceRefreshService | None = None,
        side_evidence: DeterministicSideEvidenceService | None = None,
        trusted_orderbook: TrustedOrderbookEvidenceService | None = None,
        neuron_intelligence: NeuronIntelligenceService | None = None,
        neural_event_bus: NeuralEventBusService | None = None,
        downstream_recompute: DownstreamEvidenceRecomputeService | None = None,
        post_side_readiness: PostSideRiskExitReadinessService | None = None,
        eligibility_recovery: CandidateEligibilityRecoveryService | None = None,
        paper_intent_gate: PaperIntentGateService | None = None,
        paper_execution: PaperExecutionService | None = None,
        paper_exit_loop: PaperExitLoopService | None = None,
    ):
        self._settings = settings
        self._gamma_client = gamma_client
        self._scorer = OpportunityScorer()
        self._lock = asyncio.Lock()
        self._raw_events: list[dict] = []
        self._markets: list[NormalizedMarket] = []
        self._scored_markets: list[ScoredMarket] = []
        self._last_refresh_at: datetime | None = None
        self._last_refresh_duration_ms: float | None = None
        self._last_error: str | None = None
        database_settings = get_database_settings()
        self._db_factory = DatabaseConnectionFactory(database_settings)
        self._cycle_recorder = CycleRecorder()
        self._market_snapshot_recorder = MarketSnapshotRecorder()
        self._ranking_snapshot_recorder = RankingSnapshotRecorder()
        self._runtime_intelligence = runtime_intelligence or RuntimeIntelligenceService(settings=settings)
        self._runtime_paper_trading = RuntimePaperTradingService(
            settings=database_settings,
            connection_factory=self._db_factory,
        )
        self._runtime_cycle_orchestrator = RuntimeCycleOrchestrator(connection_factory=self._db_factory)
        self._service_registry = ServiceRegistry(connection_factory=self._db_factory)
        self._event_bus = EventBus(connection_factory=self._db_factory)
        self._data_foundation = DataFoundationService(connection_factory=self._db_factory, event_bus=self._event_bus)
        self._brain_mesh_activation = brain_mesh_activation or BrainMeshActivationService(connection_factory=self._db_factory)
        self._brain_dialogue = brain_dialogue or BrainDialogueService(connection_factory=self._db_factory)
        self._evidence_refresh = evidence_refresh or EvidenceRefreshService(connection_factory=self._db_factory)
        self._side_evidence = side_evidence or DeterministicSideEvidenceService(connection_factory=self._db_factory)
        self._trusted_orderbook = trusted_orderbook or TrustedOrderbookEvidenceService(connection_factory=self._db_factory)
        self._neuron_intelligence = neuron_intelligence or NeuronIntelligenceService(connection_factory=self._db_factory)
        self._neural_event_bus = neural_event_bus or NeuralEventBusService(connection_factory=self._db_factory)
        self._downstream_recompute = downstream_recompute or DownstreamEvidenceRecomputeService(connection_factory=self._db_factory)
        self._post_side_readiness = post_side_readiness or PostSideRiskExitReadinessService(connection_factory=self._db_factory)
        self._eligibility_recovery = eligibility_recovery or CandidateEligibilityRecoveryService(connection_factory=self._db_factory)
        self._paper_intent_gate = paper_intent_gate or PaperIntentGateService(connection_factory=self._db_factory)
        self._paper_execution = paper_execution or PaperExecutionService(connection_factory=self._db_factory)
        self._paper_exit_loop = paper_exit_loop or PaperExitLoopService(connection_factory=self._db_factory)

    async def refresh(self) -> None:
        started = perf_counter()
        orchestrator = self._runtime_cycle_orchestrator
        v2_cycle_id = orchestrator.start_cycle(metadata={"source": "market_service.refresh"})
        started_event = self._publish_event(
            EventType.RUNTIME_CYCLE_STARTED.value,
            {"source": "market_service.refresh", "cycle_id": v2_cycle_id},
            aggregate_type="runtime_cycle",
            aggregate_id=v2_cycle_id,
            correlation_id=v2_cycle_id,
            cycle_id=v2_cycle_id,
        )
        try:
            orchestrator.run_stage_guard("scanner", RuntimeAction.COLLECT_DATA)
            orchestrator.mark_stage_started("scanner")
            events = await self._gamma_client.fetch_active_events()
            orchestrator.mark_stage_finished("scanner")
        except Exception as exc:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            async with self._lock:
                self._last_refresh_duration_ms = duration_ms
                self._last_error = str(exc)
            logger.exception("refresh_fetch_failed duration_ms=%s", duration_ms)
            orchestrator.finish_cycle(status="FAILED", error_count=1, metadata={"last_error": str(exc), "v2_cycle_id": v2_cycle_id})
            self._publish_event(
                EventType.RUNTIME_CYCLE_FINISHED.value,
                {"source": "market_service.refresh", "status": "FAILED", "duration_ms": duration_ms},
                aggregate_type="runtime_cycle",
                aggregate_id=v2_cycle_id,
                correlation_id=v2_cycle_id,
                causation_id=started_event.event_id if started_event else None,
                cycle_id=v2_cycle_id,
            )
            return

        normalized_markets: list[NormalizedMarket] = []
        skipped_markets = 0

        for event_index, event in enumerate(events):
            for market_payload in event.get("markets", []):
                try:
                    market = self._normalize_market(event, market_payload)
                except Exception as exc:
                    skipped_markets += 1
                    logger.warning(
                        "market_normalization_failed event_id=%s market_id=%s error=%s",
                        event.get("id"),
                        market_payload.get("id"),
                        exc,
                    )
                    continue

                if market is not None:
                    normalized_markets.append(market)

            if event_index and event_index % 50 == 0:
                await asyncio.sleep(0)

        scored_markets = await asyncio.to_thread(self._rank_markets, normalized_markets)
        last_refresh_at = datetime.now(UTC)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        cycle_id = await asyncio.to_thread(
            self._persist_runtime_snapshot,
            scored_markets=scored_markets,
            last_refresh_at=last_refresh_at,
            events_count=len(events),
        )
        data_foundation_stats = await asyncio.to_thread(
            self._data_foundation.process_markets,
            normalized_markets,
            cycle_id=cycle_id,
            correlation_id=v2_cycle_id,
            limit=self._settings.market_universe_persist_limit,
        )
        self._publish_event(
            EventType.MARKET_SNAPSHOT_CREATED.value,
            {
                "events_count": len(events),
                "normalized_markets": len(normalized_markets),
                "scored_markets": len(scored_markets),
                "persisted_cycle_id": cycle_id,
                "data_foundation": data_foundation_stats,
            },
            aggregate_type="cycle",
            aggregate_id=cycle_id or v2_cycle_id,
            correlation_id=v2_cycle_id,
            causation_id=started_event.event_id if started_event else None,
            cycle_id=v2_cycle_id,
        )
        try:
            if orchestrator.should_run_stage("intelligence"):
                orchestrator.mark_stage_started("intelligence")
                await asyncio.to_thread(
                    self._runtime_intelligence.refresh,
                    cycle_id=cycle_id,
                    scored_markets=scored_markets,
                )
                await asyncio.to_thread(
                    self._brain_mesh_activation.run_activation,
                    cycle_id=v2_cycle_id,
                    phase1_cycle_id=cycle_id,
                    limit=self._settings.top_n,
                )
                await asyncio.to_thread(
                    self._evidence_refresh.run_refresh,
                    cycle_id=v2_cycle_id,
                    limit=self._settings.top_n,
                )
                await asyncio.to_thread(
                    self._side_evidence.run_recovery,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                await asyncio.to_thread(
                    self._trusted_orderbook.resolve,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                await asyncio.to_thread(
                    self._neuron_intelligence.run_pack,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                await asyncio.to_thread(
                    self._downstream_recompute.run_recompute,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                await asyncio.to_thread(
                    self._post_side_readiness.run_recovery,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                await asyncio.to_thread(
                    self._eligibility_recovery.run_recovery,
                    cycle_id=v2_cycle_id,
                    limit=max(self._settings.top_n, 100),
                )
                orchestrator.mark_stage_finished("intelligence")
        except Exception:
            logger.exception("runtime_intelligence_or_brain_mesh_refresh_failed cycle_id=%s", cycle_id)
        try:
            if orchestrator.should_run_stage("paper"):
                orchestrator.mark_stage_started("paper")
                logger.info(
                    "legacy_runtime_paper_engine_disabled_safe_paper_execution_only cycle_id=%s",
                    cycle_id,
                )
                orchestrator.mark_stage_finished("paper")
            else:
                logger.info("runtime_paper_engine_blocked_by_mode cycle_id=%s", cycle_id)
        except RuntimePermissionDenied:
            logger.info("runtime_paper_engine_blocked_by_mode cycle_id=%s", cycle_id)

        try:
            await asyncio.to_thread(
                self._paper_intent_gate.build_intents,
                limit=100,
                write_intents=True,
                write_no_trade=True,
            )
            await asyncio.to_thread(
                self._paper_execution.run_execution,
                limit=100,
                cycle_id=v2_cycle_id,
                correlation_id=v2_cycle_id,
            )
        except Exception:
            logger.exception("paper_intent_or_execution_stage_failed cycle_id=%s", cycle_id)

        try:
            await asyncio.to_thread(
                self._paper_exit_loop.run_exit_loop,
                limit=100,
                correlation_id=v2_cycle_id,
            )
        except Exception:
            logger.exception("paper_exit_loop_failed cycle_id=%s", cycle_id)

        try:
            await asyncio.to_thread(
                self._neural_event_bus.publish_source_backed_events,
                cycle_id=v2_cycle_id,
                limit_per_source=100,
            )
            await asyncio.to_thread(self._neural_event_bus.deliver_pending, limit=250)
        except Exception:
            logger.exception("neural_event_bus_foundation_stage_failed cycle_id=%s", cycle_id)

        try:
            await asyncio.to_thread(self._brain_dialogue.materialize_recent, limit_per_source=50)
        except Exception:
            logger.exception("brain_dialogue_materialization_failed cycle_id=%s", cycle_id)

        async with self._lock:
            self._raw_events = events
            self._markets = normalized_markets
            self._scored_markets = scored_markets
            self._last_refresh_at = last_refresh_at
            self._last_refresh_duration_ms = duration_ms
            self._last_error = None

        logger.info(
            "refresh_complete events=%s markets=%s scored=%s skipped=%s duration_ms=%s",
            len(events),
            len(normalized_markets),
            len(scored_markets),
            skipped_markets,
            duration_ms,
        )
        orchestrator.finish_cycle(status="COMPLETED", metadata={"phase1_cycle_id": cycle_id})
        self._publish_event(
            EventType.RUNTIME_CYCLE_FINISHED.value,
            {
                "source": "market_service.refresh",
                "status": "COMPLETED",
                "duration_ms": duration_ms,
                "phase1_cycle_id": cycle_id,
            },
            aggregate_type="runtime_cycle",
            aggregate_id=v2_cycle_id,
            correlation_id=v2_cycle_id,
            causation_id=started_event.event_id if started_event else None,
            cycle_id=v2_cycle_id,
        )
        self._service_registry.mark_success("market_service", {"phase1_cycle_id": cycle_id})
        self._service_registry.mark_success("data_foundation", data_foundation_stats)
        await asyncio.to_thread(render_top_markets_table, scored_markets[: self._settings.top_n])

    def _publish_event(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        cycle_id: str | None = None,
    ):
        try:
            return self._event_bus.publish(
                event_type,
                payload,
                source_service="market_service",
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                cycle_id=cycle_id,
                metadata={"non_trading_event": True},
            )
        except Exception:
            logger.exception("market_service_event_publish_failed event_type=%s", event_type)
            return None

    def _rank_markets(self, markets: list[NormalizedMarket]) -> list[ScoredMarket]:
        scored = [self._scorer.score_market(market) for market in markets]
        scored.sort(
            key=lambda item: (
                item.score,
                item.market.volume_24h or 0.0,
                item.market.liquidity or 0.0,
            ),
            reverse=True,
        )
        logger.info("score_pipeline_complete scored=%s top_n=%s", len(scored), self._settings.top_n)
        return scored

    def _persist_runtime_snapshot(
        self,
        *,
        scored_markets: list[ScoredMarket],
        last_refresh_at: datetime,
        events_count: int,
    ) -> str | None:
        if not self._db_factory.enabled:
            return None
        persisted_markets = scored_markets[: self._settings.top_n]

        try:
            with self._db_factory.connect() as conn, conn.transaction():
                cycle_id, started_perf = self._cycle_recorder.open_cycle(
                    conn,
                    mode="SCAN_ONLY",
                    trigger_source="runtime.market_service",
                    top_n=self._settings.top_n,
                    pages_requested=self._settings.gamma_max_pages,
                    metadata={
                        "runtime_surface": "canonical_local_runtime",
                        "refresh_interval_seconds": self._settings.refresh_interval_seconds,
                    },
                )
                market_snapshot_ids = self._market_snapshot_recorder.record_many(
                    conn,
                    [
                        self._build_market_snapshot_contract(item=item, cycle_id=cycle_id)
                        for item in persisted_markets
                    ],
                )
                self._ranking_snapshot_recorder.record_many(
                    conn,
                    [
                        self._build_ranking_snapshot_contract(
                            item=item,
                            cycle_id=cycle_id,
                            position=position,
                            market_snapshot_id=market_snapshot_ids[item.market.market_id],
                        )
                        for position, item in enumerate(persisted_markets, start=1)
                    ],
                )
                self._cycle_recorder.close_cycle(
                    conn,
                    cycle_id=cycle_id,
                    started_perf=started_perf,
                    status="COMPLETED",
                    markets_fetched_count=events_count,
                    markets_scored_count=len(scored_markets),
                    markets_ranked_count=len(persisted_markets),
                    decisions_count=0,
                    selected_market_id=(
                        persisted_markets[0].market.market_id if persisted_markets else None
                    ),
                )
            return cycle_id
        except Exception:
            logger.exception("runtime_snapshot_persist_failed")
            return None

    def _build_market_snapshot_contract(
        self,
        *,
        item: ScoredMarket,
        cycle_id: str,
    ) -> MarketSnapshotContract:
        return MarketSnapshotContract(
            cycle_id=cycle_id,
            market_id=item.market.market_id,
            event_id=item.market.event_id,
            question=item.market.question,
            slug=item.market.slug,
            captured_at=item.computed_at,
            yes_price=item.market.yes_price,
            no_price=item.market.no_price,
            last_trade_price=item.market.last_trade_price,
            best_bid=item.market.best_bid,
            best_ask=item.market.best_ask,
            spread=item.market.spread,
            tick_size=None,
            liquidity=item.market.liquidity,
            volume=item.market.volume,
            volume_24h=item.market.volume_24h,
            open_interest=item.market.open_interest,
            comment_count=item.market.comment_count,
            competitive=item.market.competitive,
            neg_risk=None,
            orderbook_enabled=None,
            accepting_orders=item.market.accepting_orders,
            time_to_close_seconds=self._time_to_close_seconds(item.market.end_time),
            raw_payload=item.market.raw_market,
        )

    @staticmethod
    def _build_ranking_snapshot_contract(
        *,
        item: ScoredMarket,
        cycle_id: str,
        position: int,
        market_snapshot_id: int,
    ) -> RankingSnapshotContract:
        return RankingSnapshotContract(
            cycle_id=cycle_id,
            market_snapshot_id=market_snapshot_id,
            market_id=item.market.market_id,
            rank_position=position,
            base_score=float(item.score),
            adaptive_rank=float(item.score),
            selected_flag=position == 1,
            eligible_flag=True,
            reject_reason=None,
            ranking_breakdown={
                "reason": item.reason,
                "price_attractiveness": item.breakdown.price_attractiveness,
                "time_to_close": item.breakdown.time_to_close,
                "liquidity_volume": item.breakdown.liquidity_volume,
                "market_activity": item.breakdown.market_activity,
            },
            recommendation_action=None,
            recommendation_confidence=None,
            recommendation_reason=item.reason,
        )

    @staticmethod
    def _time_to_close_seconds(end_time: datetime | None) -> int | None:
        if end_time is None:
            return None
        remaining_seconds = (end_time - datetime.now(UTC)).total_seconds()
        return round(max(remaining_seconds, 0.0))

    def _normalize_market(self, event: dict, market_payload: dict) -> NormalizedMarket | None:
        is_active = bool(market_payload.get("active", False))
        is_closed = bool(market_payload.get("closed", False))
        accepting_orders = bool(market_payload.get("acceptingOrders", False))

        if not is_active or is_closed or not accepting_orders:
            return None

        outcome_prices = self._parse_json_list(market_payload.get("outcomePrices"))
        yes_price = self._coerce_price(market_payload.get("lastTradePrice"))
        if yes_price is None and outcome_prices:
            yes_price = self._coerce_price(outcome_prices[0])

        no_price = None
        if len(outcome_prices) > 1:
            no_price = self._coerce_price(outcome_prices[1])
        elif yes_price is not None:
            no_price = round(1 - yes_price, 4)

        best_bid = self._coerce_price(market_payload.get("bestBid"))
        best_ask = self._coerce_price(market_payload.get("bestAsk"))
        spread = self._coerce_non_negative(market_payload.get("spread"))
        if spread is None and best_bid is not None and best_ask is not None:
            spread = round(max(best_ask - best_bid, 0.0), 4)

        market = NormalizedMarket(
            market_id=str(market_payload["id"]),
            event_id=str(event["id"]),
            event_title=str(
                event.get("title") or market_payload.get("question") or "Untitled event"
            ),
            question=str(market_payload.get("question") or event.get("title") or "Untitled market"),
            slug=market_payload.get("slug"),
            end_time=parse_datetime(market_payload.get("endDate") or event.get("endDate")),
            yes_price=yes_price,
            no_price=no_price,
            last_trade_price=self._coerce_price(market_payload.get("lastTradePrice")),
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            liquidity=self._coerce_non_negative(
                market_payload.get("liquidityNum")
                or market_payload.get("liquidityClob")
                or market_payload.get("liquidity")
                or event.get("liquidity")
                or event.get("liquidityClob")
            ),
            volume=self._coerce_non_negative(
                market_payload.get("volumeNum") or market_payload.get("volume")
            ),
            volume_24h=self._coerce_non_negative(
                market_payload.get("volume24hr")
                or market_payload.get("volume24hrClob")
                or event.get("volume24hr")
            ),
            open_interest=self._coerce_non_negative(
                market_payload.get("openInterest") or event.get("openInterest")
            ),
            comment_count=self._coerce_int(event.get("commentCount")),
            competitive=self._coerce_non_negative(
                market_payload.get("competitive") or event.get("competitive")
            ),
            accepting_orders=accepting_orders,
            updated_at=parse_datetime(market_payload.get("updatedAt") or event.get("updatedAt")),
            raw_market=market_payload,
        )
        return market

    async def snapshot(self) -> dict:
        async with self._lock:
            top_markets = [
                item.model_dump(mode="json", exclude={"market": {"raw_market": True}})
                for item in self._scored_markets[: self._settings.top_n]
            ]
            return {
                "raw_event_count": len(self._raw_events),
                "market_count": len(self._markets),
                "top_markets": top_markets,
                "last_refresh_at": self._last_refresh_at,
                "last_refresh_duration_ms": self._last_refresh_duration_ms,
                "last_error": self._last_error,
            }

    async def top_markets(self, limit: int | None = None) -> list[ScoredMarket]:
        async with self._lock:
            return list(self._scored_markets[: limit or self._settings.top_n])

    async def raw_counts(self) -> dict:
        async with self._lock:
            return {
                "raw_event_count": len(self._raw_events),
                "normalized_market_count": len(self._markets),
                "scored_market_count": len(self._scored_markets),
            }

    async def last_refresh(self) -> dict:
        async with self._lock:
            return {
                "last_refresh_at": self._last_refresh_at,
                "last_refresh_duration_ms": self._last_refresh_duration_ms,
                "last_error": self._last_error,
            }

    async def health(self) -> dict:
        async with self._lock:
            status = "ok" if self._last_refresh_at and not self._last_error else "degraded"
            return {
                "status": status,
                "last_refresh_at": self._last_refresh_at,
                "market_count": len(self._markets),
                "last_error": self._last_error,
            }

    async def aclose(self) -> None:
        await self._gamma_client.aclose()

    @staticmethod
    def _parse_json_list(value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
            except json.JSONDecodeError:
                return []
            return loaded if isinstance(loaded, list) else []
        return []

    @staticmethod
    def _coerce_price(value) -> float | None:
        coerced = MarketService._coerce_non_negative(value)
        if coerced is None:
            return None
        return max(0.0, min(coerced, 1.0))

    @staticmethod
    def _coerce_non_negative(value) -> float | None:
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0.0)

    @staticmethod
    def _coerce_int(value) -> int | None:
        if value in (None, ""):
            return None
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return None
