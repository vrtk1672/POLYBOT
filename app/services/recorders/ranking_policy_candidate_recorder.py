from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.ranking_policy_candidate import RankingPolicyCandidateContract
from app.repositories.ranking_policy_candidates_repository import RankingPolicyCandidatesRepository


class RankingPolicyCandidateRecorder:
    def __init__(self, repository: RankingPolicyCandidatesRepository | None = None) -> None:
        self._repository = repository or RankingPolicyCandidatesRepository()

    def record(self, conn: Connection, contract: RankingPolicyCandidateContract) -> None:
        self._repository.insert(conn, contract)
