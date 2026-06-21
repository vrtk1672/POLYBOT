from __future__ import annotations

from app.domain.contracts.paper_order_event import PaperOrderEventContract
from app.repositories.paper_order_events_repository import PaperOrderEventsRepository


class PaperOrderEventRecorder:
    def __init__(self, repository: PaperOrderEventsRepository | None = None) -> None:
        self._repository = repository or PaperOrderEventsRepository()

    def record(self, conn, event: PaperOrderEventContract) -> None:
        self._repository.append(conn, event)
