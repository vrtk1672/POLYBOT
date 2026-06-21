from __future__ import annotations

from app.domain.contracts.shadow_position_event import ShadowPositionEventContract
from app.repositories.shadow_position_events_repository import ShadowPositionEventsRepository


class ShadowPositionEventRecorder:
    def __init__(self, repository: ShadowPositionEventsRepository | None = None) -> None:
        self._repository = repository or ShadowPositionEventsRepository()

    def record(self, conn, event: ShadowPositionEventContract) -> None:
        self._repository.append(conn, event)
