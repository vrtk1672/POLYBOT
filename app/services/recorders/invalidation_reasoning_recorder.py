from __future__ import annotations

from app.domain.contracts.invalidation_reasoning import InvalidationReasoningContract
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository


class InvalidationReasoningRecorder:
    def __init__(self, repository: InvalidationReasoningsRepository | None = None) -> None:
        self._repository = repository or InvalidationReasoningsRepository()

    def record(self, conn, reasoning: InvalidationReasoningContract) -> None:
        self._repository.insert(conn, reasoning)
