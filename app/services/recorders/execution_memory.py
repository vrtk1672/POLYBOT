from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.order import LiveOrderContract
from app.domain.contracts.order_status_event import OrderStatusEventContract
from app.domain.contracts.position import PositionContract
from app.domain.contracts.position_event import PositionEventContract
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.live_orders_repository import LiveOrdersRepository
from app.repositories.order_status_history_repository import OrderStatusHistoryRepository
from app.repositories.position_events_repository import PositionEventsRepository
from app.repositories.positions_repository import PositionsRepository
from app.services.recorders.order_recorder import OrderRecorder
from app.services.recorders.order_status_recorder import OrderStatusRecorder
from app.services.recorders.position_event_recorder import PositionEventRecorder
from app.services.recorders.position_recorder import PositionRecorder

logger = logging.getLogger(__name__)

EXPOSURE_STATUSES = {"FILLED", "MATCHED", "PARTIALLY_FILLED"}


@dataclass(slots=True)
class ExecutionOrderHandle:
    order_id: str
    client_order_id: str
    cycle_id: str | None
    decision_id: str | None
    market_id: str
    token_id: str
    side: str
    action: str
    price: float
    size: float
    notional: float
    status: str
    exchange_status: str | None = None
    exchange_order_id: str | None = None


class ExecutionMemoryPersistenceService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._decisions = DecisionLedgerRepository()
        self._orders = LiveOrdersRepository()
        self._order_history = OrderStatusHistoryRepository()
        self._positions = PositionsRepository()
        self._position_events = PositionEventsRepository()
        self._order_recorder = OrderRecorder(self._orders)
        self._order_status_recorder = OrderStatusRecorder(self._order_history)
        self._position_recorder = PositionRecorder(self._positions)
        self._position_event_recorder = PositionEventRecorder(self._position_events)

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def record_submission_requested(
        self,
        *,
        cycle_id: str | None,
        intent,
        raw_request: dict[str, object],
    ) -> ExecutionOrderHandle | None:
        if not self.enabled:
            return None

        order_handle = ExecutionOrderHandle(
            order_id=str(uuid4()),
            client_order_id=str(uuid4()),
            cycle_id=cycle_id,
            decision_id=None,
            market_id=intent.market_id,
            token_id=intent.token_id,
            side=intent.side,
            action=intent.action,
            price=float(intent.price),
            size=float(intent.size),
            notional=float(intent.notional_usd),
            status="SUBMISSION_REQUESTED",
        )
        try:
            with self._factory.connect() as conn, conn.transaction():
                decision_id = None
                if cycle_id:
                    decision_row = self._decisions.get_for_cycle_market(
                        conn,
                        cycle_id=cycle_id,
                        market_id=intent.market_id,
                    )
                    if decision_row:
                        decision_id = str(decision_row["id"])
                order_handle.decision_id = decision_id
                self._order_recorder.record(
                    conn,
                    LiveOrderContract(
                        id=order_handle.order_id,
                        client_order_id=order_handle.client_order_id,
                        cycle_id=cycle_id,
                        decision_id=decision_id,
                        market_id=intent.market_id,
                        token_id=intent.token_id,
                        side=intent.side,
                        action=intent.action,
                        price=float(intent.price),
                        size=float(intent.size),
                        notional=float(intent.notional_usd),
                        status=order_handle.status,
                        exchange_status=None,
                        exchange_order_id=None,
                        raw_request=raw_request,
                        raw_response={},
                    ),
                )
                self._append_order_status(
                    conn,
                    order_id=order_handle.order_id,
                    old_status=None,
                    new_status=order_handle.status,
                    source="runtime",
                    reason="submission_requested",
                    exchange_status=None,
                    raw_payload=raw_request,
                )
            return order_handle
        except Exception:
            logger.exception("execution_memory_submission_requested_failed")
            return None

    def record_submission_error(
        self,
        *,
        handle: ExecutionOrderHandle,
        error: Exception,
        raw_payload: dict[str, object],
    ) -> None:
        self._update_order_state(
            handle=handle,
            new_status="ERROR",
            exchange_status=None,
            exchange_order_id=None,
            source="runtime",
            reason=str(error),
            raw_response=raw_payload,
            error_text=str(error),
        )

    def record_submission_response(
        self,
        *,
        handle: ExecutionOrderHandle,
        response: dict[str, object],
    ) -> None:
        response_payload = response.get("response", {})
        exchange_order_id = _extract_exchange_order_id(response_payload)
        exchange_status = _extract_exchange_status(response_payload)
        new_status = _normalize_order_status(exchange_status, response_payload)
        self._update_order_state(
            handle=handle,
            new_status=new_status,
            exchange_status=exchange_status,
            exchange_order_id=exchange_order_id,
            source="exchange_submit",
            reason="submission_response",
            raw_response=response,
            error_text=None,
        )

    def record_status_lookup(
        self,
        *,
        handle: ExecutionOrderHandle,
        status_payload: dict[str, object],
    ) -> None:
        exchange_status = _extract_exchange_status(status_payload)
        new_status = _normalize_order_status(exchange_status, status_payload)
        exchange_order_id = (
            _extract_exchange_order_id(status_payload)
            or handle.exchange_order_id
        )
        self._update_order_state(
            handle=handle,
            new_status=new_status,
            exchange_status=exchange_status,
            exchange_order_id=exchange_order_id,
            source="status_lookup",
            reason="status_lookup",
            raw_response={
                "latest_status": status_payload,
            },
            error_text=None,
        )

    def record_execution_result(
        self,
        *,
        handle: ExecutionOrderHandle,
        execution_result,
    ) -> None:
        payload = execution_result.to_payload()
        exchange_status = _extract_exchange_status(execution_result.raw_result_json)
        if exchange_status is None and execution_result.result_status:
            exchange_status = str(execution_result.result_status).upper()
        self._update_order_state(
            handle=handle,
            new_status=str(execution_result.result_status),
            exchange_status=exchange_status,
            exchange_order_id=execution_result.external_order_id,
            source="execution_adapter",
            reason=execution_result.error_text or execution_result.result_status,
            raw_response={"execution_result": payload},
            error_text=execution_result.error_text,
        )

    def _update_order_state(
        self,
        *,
        handle: ExecutionOrderHandle,
        new_status: str,
        exchange_status: str | None,
        exchange_order_id: str | None,
        source: str,
        reason: str | None,
        raw_response: dict[str, object],
        error_text: str | None,
    ) -> None:
        if not self.enabled:
            return

        old_status = handle.status
        try:
            with self._factory.connect() as conn, conn.transaction():
                current_row = self._orders.get_by_id(conn, handle.order_id)
                existing_request = (
                    dict(current_row["raw_request"])
                    if current_row and isinstance(current_row.get("raw_request"), dict)
                    else {}
                )
                existing_response = (
                    dict(current_row["raw_response"])
                    if current_row and isinstance(current_row.get("raw_response"), dict)
                    else {}
                )
                merged_response = {**existing_response, **raw_response}
                self._order_recorder.record(
                    conn,
                    LiveOrderContract(
                        id=handle.order_id,
                        client_order_id=handle.client_order_id,
                        cycle_id=handle.cycle_id,
                        decision_id=handle.decision_id,
                        market_id=handle.market_id,
                        token_id=handle.token_id,
                        side=handle.side,
                        action=handle.action,
                        price=handle.price,
                        size=handle.size,
                        notional=handle.notional,
                        status=new_status,
                        exchange_status=exchange_status,
                        exchange_order_id=exchange_order_id,
                        raw_request=existing_request,
                        raw_response=merged_response,
                        error_text=error_text,
                    ),
                )
                self._append_order_status(
                    conn,
                    order_id=handle.order_id,
                    old_status=old_status,
                    new_status=new_status,
                    source=source,
                    reason=reason,
                    exchange_status=exchange_status,
                    raw_payload=raw_response,
                )
                if _status_implies_exposure(new_status):
                    self._upsert_position_from_order(conn, handle, new_status, exchange_status)
            handle.status = new_status
            handle.exchange_status = exchange_status
            handle.exchange_order_id = exchange_order_id
        except Exception:
            logger.exception("execution_memory_update_failed order_id=%s", handle.order_id)

    def _append_order_status(
        self,
        conn,
        *,
        order_id: str,
        old_status: str | None,
        new_status: str,
        source: str,
        reason: str | None,
        exchange_status: str | None,
        raw_payload: dict[str, object],
    ) -> None:
        self._order_status_recorder.record(
            conn,
            OrderStatusEventContract(
                id=str(uuid4()),
                order_id=order_id,
                event_at=datetime.now(UTC),
                old_status=old_status,
                new_status=new_status,
                source=source,
                reason=reason,
                exchange_status=exchange_status,
                raw_payload=raw_payload,
            ),
        )

    def _upsert_position_from_order(
        self,
        conn,
        handle: ExecutionOrderHandle,
        new_status: str,
        exchange_status: str | None,
    ) -> None:
        position_side = _position_side_from_action(handle.action)
        existing = self._positions.get_open_position(
            conn,
            market_id=handle.market_id,
            side=position_side,
        )
        now = datetime.now(UTC)
        event_type = "OPENED"
        if existing:
            current_size = float(existing["size"])
            current_avg = float(existing["avg_entry"]) if existing["avg_entry"] is not None else 0.0
            new_size = current_size + handle.size
            weighted_avg = (
                ((current_size * current_avg) + (handle.size * handle.price)) / new_size
                if new_size > 0
                else handle.price
            )
            position_id = str(existing["id"])
            opened_at = existing["opened_at"]
            event_type = "INCREASED"
        else:
            new_size = handle.size
            weighted_avg = handle.price
            position_id = str(uuid4())
            opened_at = now

        self._position_recorder.record(
            conn,
            PositionContract(
                id=position_id,
                market_id=handle.market_id,
                side=position_side,
                size=new_size,
                avg_entry=weighted_avg,
                current_status="OPEN",
                unrealized=0.0,
                realized=0.0,
                thesis_state="ACTIVE",
                invalidation_state="NONE",
                opened_at=opened_at,
                updated_at=now,
                closed_at=None,
            ),
        )
        self._position_event_recorder.record(
            conn,
            PositionEventContract(
                id=str(uuid4()),
                position_id=position_id,
                event_type=event_type,
                event_at=now,
                reason=f"order_status={new_status}",
                details={
                    "order_id": handle.order_id,
                    "exchange_status": exchange_status,
                    "size": handle.size,
                    "price": handle.price,
                },
            ),
        )


def _extract_exchange_order_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("orderID") or payload.get("order_id") or payload.get("id")
    return str(value) if value else None


def _extract_exchange_status(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("status") or payload.get("state") or payload.get("orderStatus")
    return str(value).upper() if value else None


def _normalize_order_status(exchange_status: str | None, payload: object) -> str:
    if exchange_status in {"FILLED", "MATCHED"}:
        return "FILLED"
    if exchange_status in {"LIVE", "OPEN", "ACTIVE"}:
        return "LIVE"
    if exchange_status in {"REJECTED", "CANCELLED", "CANCELED"}:
        return exchange_status
    if isinstance(payload, dict):
        success_value = payload.get("success")
        if success_value is True:
            return "SUBMITTED"
        if success_value is False:
            return "ERROR"
    return exchange_status or "UNKNOWN"


def _status_implies_exposure(status: str) -> bool:
    return status in EXPOSURE_STATUSES


def _position_side_from_action(action: str) -> str:
    if action.endswith("YES"):
        return "YES"
    return "NO"
