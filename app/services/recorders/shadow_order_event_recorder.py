from __future__ import annotations

from app.domain.contracts.shadow_order_event import ShadowOrderEventContract
from app.repositories.shadow_order_events_repository import ShadowOrderEventsRepository


class ShadowOrderEventRecorder:
    def __init__(self, repository: ShadowOrderEventsRepository | None = None) -> None:
        self._repository = repository or ShadowOrderEventsRepository()

    def record(self, conn, event: ShadowOrderEventContract) -> None:
        self._repository.append(conn, event)
