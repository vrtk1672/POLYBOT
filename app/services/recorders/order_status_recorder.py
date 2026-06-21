from __future__ import annotations

from app.domain.contracts.order_status_event import OrderStatusEventContract
from app.repositories.order_status_history_repository import OrderStatusHistoryRepository


class OrderStatusRecorder:
    def __init__(self, repository: OrderStatusHistoryRepository | None = None) -> None:
        self._repository = repository or OrderStatusHistoryRepository()

    def record(self, conn, event: OrderStatusEventContract) -> bool:
        return self._repository.append(conn, event)
