from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.cognition_handoff_candidate import CognitionHandoffCandidateContract
from app.repositories.cognition_handoff_candidates_repository import CognitionHandoffCandidatesRepository


class CognitionHandoffCandidateRecorder:
    def __init__(self, repository: CognitionHandoffCandidatesRepository | None = None) -> None:
        self._repository = repository or CognitionHandoffCandidatesRepository()

    def record(self, conn: Connection, contract: CognitionHandoffCandidateContract) -> None:
        self._repository.insert(conn, contract)
