from __future__ import annotations

from app.domain.contracts.event_interpretation_run import (
    EventInterpretationRunCloseContract,
    EventInterpretationRunOpenContract,
)
from app.repositories.event_interpretation_runs_repository import EventInterpretationRunsRepository


class EventInterpretationRunRecorder:
    def __init__(self, repository: EventInterpretationRunsRepository | None = None) -> None:
        self._repository = repository or EventInterpretationRunsRepository()

    def open_run(self, conn, run: EventInterpretationRunOpenContract) -> None:
        self._repository.open_run(conn, run)

    def close_run(self, conn, run: EventInterpretationRunCloseContract) -> None:
        self._repository.close_run(conn, run)
