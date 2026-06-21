from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.paper_order import PaperOrderContract
from app.domain.contracts.paper_order_event import PaperOrderEventContract
from app.domain.contracts.paper_position import PaperPositionContract
from app.domain.contracts.paper_position_event import PaperPositionEventContract
from app.domain.contracts.paper_run import PaperRunCloseContract
from app.repositories.paper_order_events_repository import PaperOrderEventsRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_position_events_repository import PaperPositionEventsRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.repositories.paper_runs_repository import PaperRunsRepository
from app.repositories.paper_signals_repository import PaperSignalsRepository
from app.services.execution_adapters import build_execution_adapter
from app.services.execution_contract import ExecutionAdapter, ExecutionIntent
from app.services.recorders.paper_order_event_recorder import PaperOrderEventRecorder
from app.services.recorders.paper_order_recorder import PaperOrderRecorder
from app.services.recorders.paper_position_event_recorder import PaperPositionEventRecorder
from app.services.recorders.paper_position_recorder import PaperPositionRecorder
from app.services.signal_paper import SignalPaperService
from app.stage4 import Stage4ExecutionClient, get_stage4_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionAwarePaperRunResult:
    paper_run_id: str
    paper_orders_count: int
    open_orders_count: int
    open_positions_count: int


class ExecutionAwarePaperService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        signal_service: SignalPaperService | None = None,
        execution_client: Stage4ExecutionClient | None = None,
        execution_adapter: ExecutionAdapter | None = None,
        execution_backend: str | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._stage4_settings = get_stage4_settings()
        self._signal_service = signal_service or SignalPaperService(
            settings=self._settings,
            connection_factory=self._factory,
        )
        self._execution_client = execution_client or Stage4ExecutionClient(self._stage4_settings)
        self._execution_backend = (execution_backend or os.getenv("POLYBOT_EXECUTION_BACKEND", "paper")).strip().lower()
        self._execution_adapter = execution_adapter or build_execution_adapter(
            backend_target=self._execution_backend,
            settings=self._stage4_settings,
            execution_client=self._execution_client,
        )
        self._paper_runs = PaperRunsRepository()
        self._paper_signals = PaperSignalsRepository()
        self._paper_orders = PaperOrdersRepository()
        self._paper_order_events = PaperOrderEventsRepository()
        self._paper_positions = PaperPositionsRepository()
        self._paper_position_events = PaperPositionEventsRepository()
        self._paper_order_recorder = PaperOrderRecorder(self._paper_orders)
        self._paper_order_event_recorder = PaperOrderEventRecorder(self._paper_order_events)
        self._paper_position_recorder = PaperPositionRecorder(self._paper_positions)
        self._paper_position_event_recorder = PaperPositionEventRecorder(self._paper_position_events)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def record_cycle(self, cycle_result) -> ExecutionAwarePaperRunResult | None:
        signal_run = self._signal_service.record_cycle(
            cycle_result,
            mode="EXECUTION_AWARE_PAPER",
        )
        if signal_run is None:
            return None
        return self.execute_existing_run(
            paper_run_id=signal_run.paper_run_id,
            cycle_result=cycle_result,
        )

    def execute_existing_run(
        self,
        *,
        paper_run_id: str,
        cycle_result,
    ) -> ExecutionAwarePaperRunResult | None:
        if not self.enabled:
            return None

        market_map = {item.market.market_id: item for item in cycle_result.top_scored}
        try:
            with self._factory.connect() as conn, conn.transaction():
                signals = self._paper_signals.list_for_run(conn, paper_run_id)
                order_count = 0
                for signal in signals:
                    if signal["signal_type"] != "WOULD_ENTER":
                        continue
                    order_count += 1
                    self._execute_signal_intent(
                        conn,
                        paper_run_id=paper_run_id,
                        signal=signal,
                        market_item=market_map.get(str(signal["market_id"])),
                    )

                open_orders = self._paper_orders.list_open_for_run(conn, paper_run_id)
                open_positions = self._paper_positions.list_open_for_run(conn, paper_run_id)
                paper_run = self._paper_runs.get_by_id(conn, paper_run_id)
                existing_metadata = (
                    dict(paper_run["metadata_json"])
                    if paper_run and isinstance(paper_run.get("metadata_json"), dict)
                    else {}
                )
                self._paper_runs.close_run(
                    conn,
                    PaperRunCloseContract(
                        id=paper_run_id,
                        ended_at=datetime.now(UTC),
                        status="COMPLETED",
                        markets_seen_count=int(paper_run["markets_seen_count"]) if paper_run else len(cycle_result.top_scored),
                        markets_ranked_count=int(paper_run["markets_ranked_count"]) if paper_run else 0,
                        candidates_selected_count=int(paper_run["candidates_selected_count"]) if paper_run else 0,
                        signals_emitted_count=int(paper_run["signals_emitted_count"]) if paper_run else len(signals),
                        metadata_json={
                            **existing_metadata,
                            "execution_aware": {
                                "paper_orders_count": order_count,
                                "open_orders_count": len(open_orders),
                                "open_positions_count": len(open_positions),
                                "execution_backend": self._execution_backend,
                            },
                        },
                    ),
                )
            return ExecutionAwarePaperRunResult(
                paper_run_id=paper_run_id,
                paper_orders_count=order_count,
                open_orders_count=len(open_orders),
                open_positions_count=len(open_positions),
            )
        except Exception:
            logger.exception("execution_aware_paper_failed paper_run_id=%s", paper_run_id)
            return None

    def _execute_signal_intent(self, conn, *, paper_run_id: str, signal: dict[str, object], market_item) -> None:
        payload = dict(signal["payload_json"]) if isinstance(signal.get("payload_json"), dict) else {}
        execution_intent = self._build_execution_intent(
            paper_run_id=paper_run_id,
            signal=signal,
            market_item=market_item,
            payload=payload,
        )
        result = self._execution_adapter.submit_intent(execution_intent)
        intended_size = execution_intent.size
        intended_price = execution_intent.price_limit or 0.0
        notional = round(intended_price * intended_size, 6)
        min_order_size = _as_float(result.raw_result_json.get("min_order_size")) or _as_float(
            execution_intent.risk_metadata.get("min_order_size")
        ) or 0.0
        fill_ratio = round(result.filled_size / intended_size, 6) if intended_size > 0 else 0.0
        stale_at_raw = result.raw_result_json.get("stale_at") if isinstance(result.raw_result_json, dict) else None
        stale_at = datetime.fromisoformat(str(stale_at_raw)) if stale_at_raw else None

        order_id = str(uuid4())
        order = PaperOrderContract(
            id=order_id,
            paper_run_id=paper_run_id,
            paper_signal_id=str(signal["id"]),
            cycle_id=str(signal["cycle_id"]) if signal["cycle_id"] is not None else None,
            market_id=str(signal["market_id"]),
            intended_outcome=str(signal["intended_outcome"]),
            action=execution_intent.side,
            intended_price=intended_price,
            intended_size=intended_size,
            notional=notional,
            status="CREATED",
            fill_ratio=0.0,
            filled_size=0.0,
            remaining_size=intended_size,
            avg_fill_price=None,
            min_size_check_passed=intended_size >= min_order_size if min_order_size > 0 else intended_size > 0,
            stale_at=None,
            payload_json={
                **payload,
                "execution_contract": execution_intent.to_payload(),
                "simulation_inputs": {
                    "current_price": execution_intent.source_context.get("market_price"),
                    "current_spread": execution_intent.risk_metadata.get("spread"),
                    "time_to_close_seconds": execution_intent.risk_metadata.get("time_to_close_seconds"),
                    "min_order_size": min_order_size,
                },
            },
        )
        self._paper_order_recorder.record(conn, order)
        self._append_order_event(
            conn,
            order_id=order_id,
            old_status=None,
            new_status="CREATED",
            reason_code="order_created",
            reason_text="paper order created from execution intent",
            payload_json={
                "paper_signal_id": str(signal["id"]),
                "execution_contract": {
                    "intent_id": execution_intent.intent_id,
                    "correlation_id": execution_intent.correlation_id,
                    "backend_target": execution_intent.backend_target,
                },
            },
        )

        order.status = result.result_status
        order.fill_ratio = fill_ratio
        order.filled_size = result.filled_size
        order.remaining_size = result.remaining_size
        order.avg_fill_price = result.avg_fill_price
        order.stale_at = stale_at
        order.payload_json = {
            **order.payload_json,
            "execution_result": result.to_payload(),
            "simulation_result": {
                "status": result.result_status,
                "fill_ratio": fill_ratio,
                "filled_size": result.filled_size,
                "remaining_size": result.remaining_size,
            },
        }
        self._paper_order_recorder.record(conn, order)
        self._append_order_event(
            conn,
            order_id=order_id,
            old_status="CREATED",
            new_status=result.result_status,
            reason_code=str(result.raw_result_json.get("reason_code") or result.error_code or "execution_result"),
            reason_text=str(result.raw_result_json.get("reason_text") or result.error_text or result.result_status),
            payload_json={
                "fill_ratio": fill_ratio,
                "stale_at": stale_at.isoformat() if stale_at else None,
                "execution_result": result.to_payload(),
            },
        )

        if result.filled_size > 0:
            self._upsert_paper_position(
                conn,
                paper_run_id=paper_run_id,
                market_id=str(signal["market_id"]),
                intended_outcome=str(signal["intended_outcome"]),
                fill_size=result.filled_size,
                fill_price=result.avg_fill_price or intended_price,
                mark_price=_market_price_for_outcome(market_item, str(signal["intended_outcome"])),
                paper_order_id=order_id,
            )

    def _build_execution_intent(
        self,
        *,
        paper_run_id: str,
        signal: dict[str, object],
        market_item,
        payload: dict[str, object],
    ) -> ExecutionIntent:
        payload_contract = payload.get("execution_intent")
        if isinstance(payload_contract, dict):
            intent = ExecutionIntent.from_payload(payload_contract)
            return ExecutionIntent(
                intent_id=str(signal["id"]),
                correlation_id=paper_run_id,
                market_id=intent.market_id,
                side=intent.side,
                order_type=intent.order_type,
                size=float(intent.size),
                price_limit=intent.price_limit,
                reason_code=intent.reason_code,
                reason_text=intent.reason_text,
                risk_metadata={
                    **intent.risk_metadata,
                    "spread": _market_spread(market_item) if market_item is not None else intent.risk_metadata.get("spread"),
                    "time_to_close_seconds": _time_to_close_seconds(market_item)
                    if market_item is not None
                    else intent.risk_metadata.get("time_to_close_seconds"),
                },
                source_context={
                    **intent.source_context,
                    "paper_run_id": paper_run_id,
                    "paper_signal_id": str(signal["id"]),
                    "cycle_id": str(signal["cycle_id"]) if signal["cycle_id"] is not None else None,
                    "market_price": _market_price_for_outcome(market_item, str(signal["intended_outcome"]))
                    if market_item is not None
                    else intent.source_context.get("market_price"),
                    "intended_outcome": str(signal["intended_outcome"]),
                },
                execution_mode="paper",
                backend_target=self._execution_backend,
                created_at=datetime.now(UTC),
            )

        legacy_intent = dict(payload.get("intent") or {})
        intended_size = _as_float(legacy_intent.get("size")) or _as_float(signal.get("intended_size")) or 0.0
        intended_price = _as_float(legacy_intent.get("price")) or _as_float(signal.get("intended_price"))
        return ExecutionIntent(
            intent_id=str(signal["id"]),
            correlation_id=paper_run_id,
            market_id=str(signal["market_id"]),
            side=str(legacy_intent.get("side") or "BUY"),
            order_type="LIMIT",
            size=intended_size,
            price_limit=intended_price,
            reason_code=str(signal["reason_code"]),
            reason_text=str(signal["reason_text"]),
            risk_metadata={
                "bucket": signal.get("bucket_type"),
                "notional_usd": _as_float(legacy_intent.get("notional")) or round((intended_price or 0.0) * intended_size, 6),
                "tick_size": legacy_intent.get("tick_size"),
                "neg_risk": legacy_intent.get("neg_risk"),
                "min_order_size": _as_float(legacy_intent.get("min_order_size")) or 0.0,
                "spread": _market_spread(market_item),
                "time_to_close_seconds": _time_to_close_seconds(market_item),
            },
            source_context={
                "token_id": legacy_intent.get("token_id"),
                "question": legacy_intent.get("question"),
                "action": legacy_intent.get("action"),
                "intended_outcome": str(signal["intended_outcome"]),
                "paper_run_id": paper_run_id,
                "paper_signal_id": str(signal["id"]),
                "cycle_id": str(signal["cycle_id"]) if signal["cycle_id"] is not None else None,
                "market_price": _market_price_for_outcome(market_item, str(signal["intended_outcome"])),
            },
            execution_mode="paper",
            backend_target=self._execution_backend,
            created_at=datetime.now(UTC),
        )

    def _upsert_paper_position(
        self,
        conn,
        *,
        paper_run_id: str,
        market_id: str,
        intended_outcome: str,
        fill_size: float,
        fill_price: float,
        mark_price: float | None,
        paper_order_id: str,
    ) -> None:
        now = datetime.now(UTC)
        existing = self._paper_positions.get_open_position(
            conn,
            paper_run_id=paper_run_id,
            market_id=market_id,
            intended_outcome=intended_outcome,
        )
        event_type = "OPENED"
        if existing:
            current_size = float(existing["size"])
            current_avg = _as_float(existing["avg_entry"]) or 0.0
            new_size = round(current_size + fill_size, 6)
            avg_entry = round(((current_size * current_avg) + (fill_size * fill_price)) / new_size, 6)
            position_id = str(existing["id"])
            opened_at = existing["opened_at"]
            event_type = "INCREASED"
        else:
            new_size = round(fill_size, 6)
            avg_entry = round(fill_price, 6)
            position_id = str(uuid4())
            opened_at = now

        current_mark = mark_price if mark_price is not None else avg_entry
        unrealized = round((current_mark - avg_entry) * new_size, 6)
        position = PaperPositionContract(
            id=position_id,
            paper_run_id=paper_run_id,
            market_id=market_id,
            intended_outcome=intended_outcome,
            size=new_size,
            avg_entry=avg_entry,
            mark_price=current_mark,
            unrealized=unrealized,
            realized=0.0,
            current_status="OPEN",
            thesis_state="ACTIVE",
            invalidation_state="NONE",
            opened_at=opened_at,
            updated_at=now,
            closed_at=None,
            payload_json={
                "last_paper_order_id": paper_order_id,
                "mark_source": "cycle_market_price",
            },
        )
        self._paper_position_recorder.record(conn, position)
        self._paper_position_event_recorder.record(
            conn,
            PaperPositionEventContract(
                id=str(uuid4()),
                paper_position_id=position_id,
                event_at=now,
                event_type=event_type,
                reason_code="simulated_fill",
                reason_text=f"paper order {paper_order_id} contributed simulated fill",
                payload_json={
                    "fill_size": fill_size,
                    "fill_price": fill_price,
                },
            ),
        )
        self._paper_position_event_recorder.record(
            conn,
            PaperPositionEventContract(
                id=str(uuid4()),
                paper_position_id=position_id,
                event_at=now,
                event_type="MARKED",
                reason_code="mark_to_market",
                reason_text="position marked using current cycle market price",
                payload_json={
                    "mark_price": current_mark,
                    "unrealized": unrealized,
                },
            ),
        )

    def _append_order_event(
        self,
        conn,
        *,
        order_id: str,
        old_status: str | None,
        new_status: str,
        reason_code: str,
        reason_text: str,
        payload_json: dict[str, object],
    ) -> None:
        self._paper_order_event_recorder.record(
            conn,
            PaperOrderEventContract(
                id=str(uuid4()),
                paper_order_id=order_id,
                event_at=datetime.now(UTC),
                old_status=old_status,
                new_status=new_status,
                reason_code=reason_code,
                reason_text=reason_text,
                payload_json=payload_json,
            ),
        )


def _market_price_for_outcome(market_item, intended_outcome: str) -> float | None:
    if market_item is None:
        return None
    if intended_outcome == "YES":
        return _as_float(market_item.market.yes_price)
    return _as_float(market_item.market.no_price)


def _market_spread(market_item) -> float | None:
    if market_item is None:
        return None
    return _as_float(market_item.market.spread)


def _time_to_close_seconds(market_item) -> int | None:
    if market_item is None:
        return None
    from gamma_crawler import hours_remaining

    remaining_hours = hours_remaining(market_item.market)
    if remaining_hours is None:
        return None
    return round(remaining_hours * 3600)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
