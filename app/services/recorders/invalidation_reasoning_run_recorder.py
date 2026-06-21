from __future__ import annotations

from app.domain.contracts.invalidation_reasoning_run import (
    InvalidationReasoningRunCloseContract,
    InvalidationReasoningRunOpenContract,
)
from app.repositories.invalidation_reasoning_runs_repository import InvalidationReasoningRunsRepository


class InvalidationReasoningRunRecorder:
    def __init__(self, repository: InvalidationReasoningRunsRepository | None = None) -> None:
        self._repository = repository or InvalidationReasoningRunsRepository()

    def open_run(self, conn, run: InvalidationReasoningRunOpenContract) -> None:
        self._repository.open_run(conn, run)

    def close_run(self, conn, run: InvalidationReasoningRunCloseContract) -> None:
        self._repository.close_run(conn, run)
