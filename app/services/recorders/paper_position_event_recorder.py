from __future__ import annotations

from app.domain.contracts.paper_position_event import PaperPositionEventContract
from app.repositories.paper_position_events_repository import PaperPositionEventsRepository


class PaperPositionEventRecorder:
    def __init__(self, repository: PaperPositionEventsRepository | None = None) -> None:
        self._repository = repository or PaperPositionEventsRepository()

    def record(self, conn, event: PaperPositionEventContract) -> None:
        self._repository.append(conn, event)
