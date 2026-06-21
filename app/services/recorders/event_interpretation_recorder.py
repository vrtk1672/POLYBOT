from __future__ import annotations

from app.domain.contracts.event_interpretation import EventInterpretationContract
from app.repositories.event_interpretations_repository import EventInterpretationsRepository


class EventInterpretationRecorder:
    def __init__(self, repository: EventInterpretationsRepository | None = None) -> None:
        self._repository = repository or EventInterpretationsRepository()

    def record(self, conn, interpretation: EventInterpretationContract) -> None:
        self._repository.insert(conn, interpretation)
