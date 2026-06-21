from __future__ import annotations

from app.domain.contracts.position_event import PositionEventContract
from app.repositories.position_events_repository import PositionEventsRepository


class PositionEventRecorder:
    def __init__(self, repository: PositionEventsRepository | None = None) -> None:
        self._repository = repository or PositionEventsRepository()

    def record(self, conn, event: PositionEventContract) -> None:
        self._repository.append(conn, event)
