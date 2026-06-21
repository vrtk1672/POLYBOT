from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.config import canonical_runtime_mode
from app.domain.contracts.paper_order import PaperOrderContract
from app.domain.contracts.paper_order_event import PaperOrderEventContract
from app.domain.contracts.paper_position import PaperPositionContract
from app.domain.contracts.paper_position_event import PaperPositionEventContract
from app.models.score import ScoredMarket
from app.repositories.command_intent_records_repository import CommandIntentRecordsRepository
from app.repositories.paper_order_events_repository import PaperOrderEventsRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_position_events_repository import PaperPositionEventsRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.runtime.modes import RuntimeAction
from app.runtime.state_governor import StateGovernor
from app.services.capital_allocator import PaperCapitalSource
from app.services.execution_adapters import build_execution_adapter
from app.services.execution_contract import ExecutionAdapter, ExecutionIntent
from app.services.advisory_resolution import AdvisoryResolutionService
from app.services.bucket_allocation import BucketAllocationService
from app.services.command_intent_staging import CommandIntentStagingService
from app.services.execution_aware_paper import ExecutionAwarePaperService
from app.services.exit_advisory import ExitAdvisoryService
from app.services.invalidation_exit_policy import InvalidationExitPolicyService
from app.services.lifecycle_governance import LifecycleGovernanceGateService
from app.services.live_runtime import LiveTradingService
from app.services.ranking_policy import RankingPolicyService
from app.services.ranking_v2 import RankingV2Service
from app.services.recorders.paper_order_event_recorder import PaperOrderEventRecorder
from app.services.recorders.paper_order_recorder import PaperOrderRecorder
from app.services.recorders.paper_position_event_recorder import PaperPositionEventRecorder
from app.services.recorders.paper_position_recorder import PaperPositionRecorder
from app.services.signal_paper import SignalPaperService
from app.services.shadow_live import ShadowLiveService
from app.services.trade_classification import TradeClassificationService
from app.stage2.claude_analyst import MarketRecommendation
from app.stage4 import Stage4ExecutionClient, get_stage4_settings

logger = logging.getLogger(__name__)

OPEN_PAPER_ORDER_STATUSES = {"CREATED", "OPEN", "PARTIALLY_FILLED"}
TERMINAL_PAPER_ORDER_STATUSES = {"FILLED", "CANCELED", "CANCELLED", "EXPIRED", "BLOCKED_MIN_SIZE"}
OPEN_PAPER_POSITION_STATUSES = {"OPEN", "EXIT_PENDING"}


@dataclass(slots=True)
class RuntimePaperCycleResult:
    all_scored: list[ScoredMarket]
    top_scored: list[ScoredMarket]
    recommendations: list[MarketRecommendation]
    cycle_id: str | None


class PaperStage4InspectionClient:
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)
        self._capital_source = PaperCapitalSource(
            settings=self._settings,
            connection_factory=self._factory,
            stage4_settings=self._stage4_settings,
        )

    def get_open_orders(self) -> list[dict[str, object]]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            order_rows = conn.execute(
                """
                SELECT market_id, updated_at AS created_at, 'ORDER' AS exposure_type
                FROM paper_orders
                WHERE status = ANY(%s)
                """,
                (list(OPEN_PAPER_ORDER_STATUSES),),
            ).fetchall()
            position_rows = conn.execute(
                """
                SELECT market_id, updated_at AS created_at, 'POSITION' AS exposure_type
                FROM paper_positions
                WHERE closed_at IS NULL
                  AND current_status = ANY(%s)
                """,
                (list(OPEN_PAPER_POSITION_STATUSES),),
            ).fetchall()
        open_exposures = [dict(row) for row in order_rows]
        open_exposures.extend(dict(row) for row in position_rows)
        return open_exposures

    def get_order_book_summary(self, token_id: str):
        return self._execution_client.get_order_book_summary(token_id)

    def get_balance_allowance(self, *, token_id: str | None = None) -> dict[str, dict[str, str | float]]:
        snapshot = self._capital_source.snapshot()
        return {
            "collateral": {
                "balance": f"{snapshot.available_cash_usd:.6f}",
                "balance_usd": round(snapshot.available_cash_usd, 6),
            },
            "capital_source_mode": snapshot.source_mode,
            "capital_source_status": snapshot.source_status,
            "capital_snapshot": snapshot.to_payload(),
        }


class PaperTradeLifecycleService:
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._command_intents = CommandIntentRecordsRepository()
        self._paper_orders = PaperOrdersRepository()
        self._paper_positions = PaperPositionsRepository()
        self._paper_order_recorder = PaperOrderRecorder(self._paper_orders)
        self._paper_position_recorder = PaperPositionRecorder(self._paper_positions)
        self._paper_order_events = PaperOrderEventRecorder(PaperOrderEventsRepository())
        self._paper_position_events = PaperPositionEventRecorder(PaperPositionEventsRepository())
        self._lifecycle_governance = LifecycleGovernanceGateService(connection_factory=self._factory)
        self._stage4_settings = get_stage4_settings()
        self._execution_adapter: ExecutionAdapter = build_execution_adapter(
            backend_target="paper",
            settings=self._stage4_settings,
        )
        self._governor = StateGovernor(connection_factory=self._factory)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def process_cycle(self, *, market_map: dict[str, ScoredMarket]) -> None:
        if not self._governor.can_execute(RuntimeAction.OPEN_PAPER_POSITION):
            logger.info("paper_trade_lifecycle_blocked_by_runtime_mode")
            return
        if not self.enabled or not market_map:
            return
        try:
            with self._factory.connect() as conn, conn.transaction():
                self._mark_open_positions(conn, market_map=market_map)
                self._apply_latest_paper_intents(conn, market_map=market_map)
        except Exception:
            logger.exception("paper_trade_lifecycle_failed")

    def _mark_open_positions(self, conn, *, market_map: dict[str, ScoredMarket]) -> None:
        for market_id, item in market_map.items():
            current_yes = _float_or_none(item.market.yes_price)
            current_no = _float_or_none(item.market.no_price)
            for row in self._paper_positions.list_for_market(conn, market_id):
                if row["closed_at"] is not None:
                    continue
                intended_outcome = str(row["intended_outcome"])
                current_mark = current_yes if intended_outcome == "YES" else current_no
                if current_mark is None:
                    current_mark = _float_or_none(row["mark_price"]) or _float_or_none(row["avg_entry"]) or 0.0
                size = _float_or_none(row["size"]) or 0.0
                avg_entry = _float_or_none(row["avg_entry"]) or current_mark
                unrealized = round((current_mark - avg_entry) * size, 6)
                payload_json = dict(row["payload_json"]) if isinstance(row.get("payload_json"), dict) else {}
                payload_json["last_mark_cycle_market_id"] = market_id
                payload_json["last_marked_at"] = datetime.now(UTC).isoformat()
                position = PaperPositionContract(
                    id=str(row["id"]),
                    paper_run_id=str(row["paper_run_id"]),
                    market_id=market_id,
                    intended_outcome=intended_outcome,
                    size=size,
                    avg_entry=avg_entry,
                    mark_price=current_mark,
                    unrealized=unrealized,
                    realized=_float_or_none(row["realized"]) or 0.0,
                    current_status=str(row["current_status"]),
                    thesis_state=str(row["thesis_state"]),
                    invalidation_state=str(row["invalidation_state"]),
                    opened_at=row["opened_at"],
                    updated_at=datetime.now(UTC),
                    closed_at=row["closed_at"],
                    payload_json=payload_json,
                )
                self._paper_position_recorder.record(conn, position)
                self._paper_position_events.record(
                    conn,
                    PaperPositionEventContract(
                        id=_new_id(),
                        paper_position_id=str(row["id"]),
                        event_at=datetime.now(UTC),
                        event_type="MARKED",
                        reason_code="runtime_mark_to_market",
                        reason_text="position marked from the latest runtime market snapshot",
                        payload_json={
                            "mark_price": current_mark,
                            "unrealized": unrealized,
                        },
                    ),
                )

    def _apply_latest_paper_intents(self, conn, *, market_map: dict[str, ScoredMarket]) -> None:
        for market_id in market_map:
            intents = self._command_intents.list_for_market(conn, market_id)
            if not intents:
                continue
            latest_run_id = str(intents[0]["command_intent_run_id"])
            latest_intents = [
                dict(row)
                for row in intents
                if str(row["command_intent_run_id"]) == latest_run_id
                and str(row["command_status_class"]) == "STAGED"
                and str(row["exposure_type"]).startswith("PAPER_")
            ]
            seen_exposures: set[tuple[str, str]] = set()
            for intent in latest_intents:
                exposure_key = (str(intent["exposure_type"]), str(intent["exposure_ref_id"]))
                if exposure_key in seen_exposures:
                    continue
                seen_exposures.add(exposure_key)
                if str(intent["exposure_type"]) == "PAPER_ORDER":
                    self._apply_order_intent(conn, intent=intent)
                elif str(intent["exposure_type"]) == "PAPER_POSITION":
                    self._apply_position_intent(conn, intent=intent, market_map=market_map)

    def _apply_order_intent(self, conn, *, intent: dict[str, object]) -> None:
        order = self._paper_orders.get_by_id(conn, str(intent["exposure_ref_id"]))
        if order is None:
            return
        if str(order["status"]) in TERMINAL_PAPER_ORDER_STATUSES:
            return
        command = str(intent["command_intent_class"])
        if command not in {"CANCEL_PENDING_ORDER", "BLOCK_NEW_ENTRY"}:
            return
        payload = order.get("payload_json") if isinstance(order.get("payload_json"), dict) else {}
        source_intent_id = payload.get("source_intent_id")
        if not source_intent_id or not self._legacy_governance_allows(
            conn,
            subject_type="PAPER_INTENT",
            subject_id=str(source_intent_id),
            command=command,
            command_intent_id=str(intent["id"]),
        ):
            logger.info("legacy_paper_order_command_blocked_by_lifecycle_governance command=%s order_id=%s", command, order["id"])
            return
        payload_json = dict(order["payload_json"]) if isinstance(order.get("payload_json"), dict) else {}
        if payload_json.get("last_applied_command_intent_id") == str(intent["id"]):
            return
        payload_json["last_applied_command_intent_id"] = str(intent["id"])
        payload_json["last_applied_command_intent_class"] = command
        updated = PaperOrderContract(
            id=str(order["id"]),
            paper_run_id=str(order["paper_run_id"]),
            paper_signal_id=str(order["paper_signal_id"]),
            cycle_id=str(order["cycle_id"]) if order["cycle_id"] is not None else None,
            market_id=str(order["market_id"]),
            intended_outcome=str(order["intended_outcome"]),
            action=str(order["action"]),
            intended_price=_float_or_none(order["intended_price"]) or 0.0,
            intended_size=_float_or_none(order["intended_size"]) or 0.0,
            notional=_float_or_none(order["notional"]) or 0.0,
            status="CANCELED",
            fill_ratio=_float_or_none(order["fill_ratio"]) or 0.0,
            filled_size=_float_or_none(order["filled_size"]) or 0.0,
            remaining_size=_float_or_none(order["remaining_size"]) or 0.0,
            avg_fill_price=_float_or_none(order["avg_fill_price"]),
            min_size_check_passed=bool(order["min_size_check_passed"]),
            stale_at=datetime.now(UTC),
            payload_json=payload_json,
        )
        self._paper_order_recorder.record(conn, updated)
        self._paper_order_events.record(
            conn,
            PaperOrderEventContract(
                id=_new_id(),
                paper_order_id=str(order["id"]),
                event_at=datetime.now(UTC),
                old_status=str(order["status"]),
                new_status="CANCELED",
                reason_code=command.lower(),
                reason_text="paper order canceled by staged paper command intent",
                payload_json={"command_intent_id": str(intent["id"])},
            ),
        )

    def _apply_position_intent(
        self,
        conn,
        *,
        intent: dict[str, object],
        market_map: dict[str, ScoredMarket],
    ) -> None:
        position = self._paper_positions.get_by_id(conn, str(intent["exposure_ref_id"]))
        if position is None or position["closed_at"] is not None:
            return
        command = str(intent["command_intent_class"])
        payload_json = dict(position["payload_json"]) if isinstance(position.get("payload_json"), dict) else {}
        if payload_json.get("last_applied_command_intent_id") == str(intent["id"]):
            return
        if not self._legacy_governance_allows(
            conn,
            subject_type="PAPER_POSITION",
            subject_id=str(position["id"]),
            command=command,
            command_intent_id=str(intent["id"]),
        ):
            logger.info("legacy_paper_position_command_blocked_by_lifecycle_governance command=%s position_id=%s", command, position["id"])
            return

        market_item = market_map.get(str(position["market_id"]))
        intended_outcome = str(position["intended_outcome"])
        current_mark = (
            _float_or_none(market_item.market.yes_price)
            if market_item is not None and intended_outcome == "YES"
            else _float_or_none(market_item.market.no_price)
            if market_item is not None
            else _float_or_none(position["mark_price"])
        )
        if current_mark is None:
            current_mark = _float_or_none(position["avg_entry"]) or 0.0

        size = _float_or_none(position["size"]) or 0.0
        avg_entry = _float_or_none(position["avg_entry"]) or current_mark
        realized = _float_or_none(position["realized"]) or 0.0
        thesis_state = str(position["thesis_state"])
        invalidation_state = str(position["invalidation_state"])
        current_status = str(position["current_status"])
        closed_at = position["closed_at"]
        event_type = None
        reason_text = None

        if command == "PREPARE_POSITION_EXIT":
            if current_status == "EXIT_PENDING":
                return
            current_status = "EXIT_PENDING"
            thesis_state = "EXIT_PENDING"
            invalidation_state = "WATCH"
            event_type = "EXIT_PREPARED"
            reason_text = "paper position marked exit-pending by staged advisory intent"
        elif command == "REDUCE_POSITION":
            reduced_size = round(size * 0.5, 6)
            execution_intent = _build_paper_exit_intent(
                intent=intent,
                position=position,
                command=command,
                size=reduced_size,
                current_mark=current_mark,
                avg_entry=avg_entry,
            )
            execution_result = self._execution_adapter.submit_intent(execution_intent)
            close_size = min(reduced_size, _float_or_none(execution_result.filled_size) or 0.0)
            if close_size <= 0:
                payload_json["last_reduce_execution_intent"] = execution_intent.to_payload()
                payload_json["last_reduce_execution_result"] = execution_result.to_payload()
                event_type = "REDUCE_BLOCKED"
                reason_text = "paper position reduction execution did not fill"
                unrealized = round((current_mark - avg_entry) * size, 6)
                updated = PaperPositionContract(
                    id=str(position["id"]),
                    paper_run_id=str(position["paper_run_id"]),
                    market_id=str(position["market_id"]),
                    intended_outcome=intended_outcome,
                    size=size,
                    avg_entry=avg_entry,
                    mark_price=current_mark,
                    unrealized=unrealized,
                    realized=round(realized, 6),
                    current_status=current_status,
                    thesis_state=thesis_state,
                    invalidation_state=invalidation_state,
                    opened_at=position["opened_at"],
                    updated_at=datetime.now(UTC),
                    closed_at=closed_at,
                    payload_json=payload_json,
                )
                self._paper_position_recorder.record(conn, updated)
                self._paper_position_events.record(
                    conn,
                    PaperPositionEventContract(
                        id=_new_id(),
                        paper_position_id=str(position["id"]),
                        event_at=datetime.now(UTC),
                        event_type=event_type,
                        reason_code=str(execution_result.error_code or execution_result.result_status).lower(),
                        reason_text=reason_text,
                        payload_json={
                            "command_intent_id": str(intent["id"]),
                            "execution_contract": execution_intent.to_payload(),
                            "execution_result": execution_result.to_payload(),
                        },
                    ),
                )
                return
            remaining_size = round(max(size - close_size, 0.0), 6)
            realized += round((current_mark - avg_entry) * close_size, 6)
            size = remaining_size
            current_status = "OPEN" if remaining_size > 0 else "EXITED"
            thesis_state = "ACTIVE" if remaining_size > 0 else "EXITED"
            invalidation_state = "REDUCED"
            closed_at = datetime.now(UTC) if remaining_size <= 0 else None
            event_type = "REDUCED"
            reason_text = "paper position reduced by staged advisory intent"
            payload_json["last_reduce_execution_intent"] = execution_intent.to_payload()
            payload_json["last_reduce_execution_result"] = execution_result.to_payload()
        elif command == "EXIT_POSITION":
            execution_intent = _build_paper_exit_intent(
                intent=intent,
                position=position,
                command=command,
                size=size,
                current_mark=current_mark,
                avg_entry=avg_entry,
            )
            execution_result = self._execution_adapter.submit_intent(execution_intent)
            close_size = min(size, _float_or_none(execution_result.filled_size) or 0.0)
            if close_size <= 0:
                payload_json["last_exit_execution_intent"] = execution_intent.to_payload()
                payload_json["last_exit_execution_result"] = execution_result.to_payload()
                event_type = "EXIT_BLOCKED"
                reason_text = "paper position exit execution did not fill"
                unrealized = round((current_mark - avg_entry) * size, 6)
                updated = PaperPositionContract(
                    id=str(position["id"]),
                    paper_run_id=str(position["paper_run_id"]),
                    market_id=str(position["market_id"]),
                    intended_outcome=intended_outcome,
                    size=size,
                    avg_entry=avg_entry,
                    mark_price=current_mark,
                    unrealized=unrealized,
                    realized=round(realized, 6),
                    current_status=current_status,
                    thesis_state=thesis_state,
                    invalidation_state=invalidation_state,
                    opened_at=position["opened_at"],
                    updated_at=datetime.now(UTC),
                    closed_at=closed_at,
                    payload_json=payload_json,
                )
                self._paper_position_recorder.record(conn, updated)
                self._paper_position_events.record(
                    conn,
                    PaperPositionEventContract(
                        id=_new_id(),
                        paper_position_id=str(position["id"]),
                        event_at=datetime.now(UTC),
                        event_type=event_type,
                        reason_code=str(execution_result.error_code or execution_result.result_status).lower(),
                        reason_text=reason_text,
                        payload_json={
                            "command_intent_id": str(intent["id"]),
                            "execution_contract": execution_intent.to_payload(),
                            "execution_result": execution_result.to_payload(),
                        },
                    ),
                )
                return
            realized += round((current_mark - avg_entry) * close_size, 6)
            current_status = "EXITED"
            thesis_state = "EXITED"
            invalidation_state = "EXITED"
            closed_at = datetime.now(UTC)
            event_type = "EXITED"
            reason_text = "paper position exited by staged advisory intent"
            payload_json["last_exit_execution_intent"] = execution_intent.to_payload()
            payload_json["last_exit_execution_result"] = execution_result.to_payload()
        else:
            return

        unrealized = round((current_mark - avg_entry) * size, 6) if closed_at is None else 0.0
        payload_json["last_applied_command_intent_id"] = str(intent["id"])
        payload_json["last_applied_command_intent_class"] = command
        updated = PaperPositionContract(
            id=str(position["id"]),
            paper_run_id=str(position["paper_run_id"]),
            market_id=str(position["market_id"]),
            intended_outcome=intended_outcome,
            size=size,
            avg_entry=avg_entry,
            mark_price=current_mark,
            unrealized=unrealized,
            realized=round(realized, 6),
            current_status=current_status,
            thesis_state=thesis_state,
            invalidation_state=invalidation_state,
            opened_at=position["opened_at"],
            updated_at=datetime.now(UTC),
            closed_at=closed_at,
            payload_json=payload_json,
        )
        self._paper_position_recorder.record(conn, updated)
        self._paper_position_events.record(
            conn,
            PaperPositionEventContract(
                id=_new_id(),
                paper_position_id=str(position["id"]),
                event_at=datetime.now(UTC),
                event_type=event_type or "UPDATED",
                reason_code=command.lower(),
                reason_text=reason_text or "paper position updated by staged intent",
                payload_json={
                    "command_intent_id": str(intent["id"]),
                    "mark_price": current_mark,
                    "realized": round(realized, 6),
                    "remaining_size": size,
                    "execution_contract": payload_json.get("last_exit_execution_intent"),
                    "execution_result": payload_json.get("last_exit_execution_result"),
                    "reduce_execution_contract": payload_json.get("last_reduce_execution_intent"),
                    "reduce_execution_result": payload_json.get("last_reduce_execution_result"),
                },
            ),
        )

    def _legacy_governance_allows(
        self,
        conn,
        *,
        subject_type: str,
        subject_id: str,
        command: str,
        command_intent_id: str,
    ) -> bool:
        decision = self._lifecycle_governance.evaluate_subject_with_conn(
            conn,
            subject_type=subject_type,
            subject_id=subject_id,
            request_action="LEGACY_PAPER_COMMAND",
            allow_build=True,
            write_decision=True,
            metadata={
                "source_layer": "legacy_runtime_paper_trading",
                "command": command,
                "command_intent_id": command_intent_id,
            },
        )
        return bool(decision.get("allow_paper_execution"))


class RuntimePaperTradingService:
    def __init__(
        self,
        *,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        execution_client: Stage4ExecutionClient | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._execution_backend = os.getenv("POLYBOT_EXECUTION_BACKEND", "paper").strip().lower()
        self._execution_mode = canonical_runtime_mode(os.getenv("POLYBOT_RUNTIME_MODE"))
        self._paper_execution_client = PaperStage4InspectionClient(
            settings=self._settings,
            connection_factory=self._factory,
            execution_client=execution_client,
        )
        signal_service = SignalPaperService(
            settings=self._settings,
            connection_factory=self._factory,
            execution_client=self._paper_execution_client,
        )
        self._execution_aware_paper = ExecutionAwarePaperService(
            settings=self._settings,
            connection_factory=self._factory,
            signal_service=signal_service,
            execution_client=self._paper_execution_client,
            execution_backend=self._execution_backend,
        )
        self._shadow_live = ShadowLiveService(
            settings=self._settings,
            connection_factory=self._factory,
            execution_client=execution_client,
        )
        self._live_trading = LiveTradingService(
            settings=self._settings,
            connection_factory=self._factory,
            execution_client=execution_client,
        )
        self._trade_classification = TradeClassificationService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._bucket_allocation = BucketAllocationService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._ranking_v2 = RankingV2Service(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._ranking_policy = RankingPolicyService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._invalidation = InvalidationExitPolicyService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._exit_advisory = ExitAdvisoryService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._resolution = AdvisoryResolutionService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._command_intents = CommandIntentStagingService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._lifecycle = PaperTradeLifecycleService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._governor = StateGovernor(connection_factory=self._factory)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def process_cycle(self, *, cycle_id: str | None, scored_markets: list[ScoredMarket]) -> None:
        if not self.enabled or not cycle_id or not scored_markets:
            return
        cycle_result = self._build_runtime_cycle_result(cycle_id=cycle_id, scored_markets=scored_markets)
        market_ids = [item.market.market_id for item in cycle_result.top_scored]
        try:
            if self._execution_mode == "PAPER":
                if not self._governor.can_execute(RuntimeAction.OPEN_PAPER_POSITION):
                    logger.info("paper_order_creation_blocked_by_runtime_mode cycle_id=%s", cycle_id)
                    return
                logger.info("legacy_execution_aware_paper_blocked_by_lifecycle_governance cycle_id=%s", cycle_id)
                lifecycle_market_ids = self._open_paper_position_market_ids()
                market_ids = _dedupe_market_ids([*market_ids, *lifecycle_market_ids])
            elif self._execution_mode == "LIVE" and self._execution_backend == "shadow_live":
                if not self._governor.can_execute(RuntimeAction.RUN_SHADOW_ENGINE):
                    logger.info("shadow_live_runtime_blocked_by_runtime_mode cycle_id=%s", cycle_id)
                    return
                self._shadow_live.record_cycle(cycle_result)
            elif self._execution_mode == "LIVE" and self._execution_backend == "live":
                if not self._governor.can_execute(RuntimeAction.SEND_LIVE_ORDER):
                    logger.info("live_runtime_blocked_by_runtime_mode cycle_id=%s", cycle_id)
                    return
                self._live_trading.record_cycle(cycle_result)
            trade_result = self._trade_classification.classify_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            if trade_result is not None:
                self._bucket_allocation.allocate_for_classification_run(
                    trade_result.trade_classification_run_id,
                    source_ref=cycle_id,
                )
            ranking_v2_result = self._ranking_v2.rank_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            if ranking_v2_result is not None:
                self._ranking_policy.apply_policy_to_ranking_run(
                    ranking_v2_result.ranking_v2_run_id,
                    source_ref=cycle_id,
                )
            self._invalidation.evaluate_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            self._exit_advisory.generate_for_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            self._resolution.generate_for_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            self._command_intents.generate_for_markets(
                market_ids,
                source_type="runtime_cycle",
                source_ref=cycle_id,
            )
            if self._execution_mode == "PAPER":
                self._lifecycle.process_cycle(
                    market_map={item.market.market_id: item for item in cycle_result.all_scored if item.market.market_id in set(market_ids)},
                )
        except Exception:
            logger.exception("runtime_paper_trading_cycle_failed cycle_id=%s", cycle_id)

    def _open_paper_position_market_ids(self) -> list[str]:
        if not self._factory.enabled:
            return []
        with self._factory.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT market_id
                FROM paper_positions
                WHERE closed_at IS NULL
                  AND current_status = ANY(%s)
                """,
                (list(OPEN_PAPER_POSITION_STATUSES),),
            ).fetchall()
        return [str(row["market_id"]) for row in rows]

    def _build_runtime_cycle_result(
        self,
        *,
        cycle_id: str,
        scored_markets: list[ScoredMarket],
    ) -> RuntimePaperCycleResult:
        top_scored = list(scored_markets[: self._stage4_settings.live_allowed_universe_top_n])
        recommendations: list[MarketRecommendation] = []
        for index, item in enumerate(top_scored, start=1):
            yes_price = _float_or_none(item.market.yes_price)
            no_price = _float_or_none(item.market.no_price)
            if yes_price is None and no_price is None:
                action = "SKIP"
            elif no_price is None or (yes_price is not None and yes_price <= no_price):
                action = "BUY_YES"
            else:
                action = "BUY_NO"
            confidence = round(
                max(self._stage4_settings.live_min_confidence, min(0.95, float(item.score) / 100.0)),
                2,
            )
            recommendations.append(
                MarketRecommendation(
                    rank=index,
                    question=item.market.question,
                    confidence=confidence,
                    action=action,
                    reason="runtime_ranked_candidate",
                    yes_price=yes_price or 0.0,
                    no_price=no_price or (round(1 - yes_price, 4) if yes_price is not None else 0.0),
                    score=float(item.score),
                    computed_at=item.computed_at.isoformat(),
                )
            )
        return RuntimePaperCycleResult(
            all_scored=list(scored_markets),
            top_scored=top_scored,
            recommendations=recommendations,
            cycle_id=cycle_id,
        )


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _new_id() -> str:
    return str(uuid4())


def _dedupe_market_ids(market_ids: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for market_id in market_ids:
        if market_id in seen:
            continue
        seen.add(market_id)
        output.append(market_id)
    return output


def _build_paper_exit_intent(
    *,
    intent: dict[str, object],
    position: dict[str, object],
    command: str,
    size: float,
    current_mark: float,
    avg_entry: float,
) -> ExecutionIntent:
    now = datetime.now(UTC)
    market_id = str(position["market_id"])
    intended_outcome = str(position["intended_outcome"])
    notional = round(size * current_mark, 6)
    return ExecutionIntent(
        intent_id=str(uuid4()),
        correlation_id=str(intent["command_intent_run_id"]),
        market_id=market_id,
        side="SELL",
        order_type="LIMIT",
        size=size,
        price_limit=current_mark,
        reason_code=str(intent["command_intent_class"]).lower(),
        reason_text=str(intent["command_reason_text"]),
        risk_metadata={
            "bucket": "paper_exit",
            "notional_usd": notional,
            "min_order_size": 0.0,
            "spread": 0.0,
            "avg_entry": avg_entry,
            "command_intent_id": str(intent["id"]),
            "command": command,
        },
        source_context={
            "position_id": str(position["id"]),
            "paper_run_id": str(position["paper_run_id"]),
            "market_id": market_id,
            "intended_outcome": intended_outcome,
            "action": f"SELL_{intended_outcome}",
            "market_price": current_mark,
        },
        execution_mode="paper",
        backend_target="paper",
        created_at=now,
    )
