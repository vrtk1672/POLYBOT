from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.ranking_v2_candidate import RankingV2CandidateContract
from app.repositories.ranking_v2_candidates_repository import RankingV2CandidatesRepository


class RankingV2CandidateRecorder:
    def __init__(self, repository: RankingV2CandidatesRepository | None = None) -> None:
        self._repository = repository or RankingV2CandidatesRepository()

    def record(self, conn: Connection, contract: RankingV2CandidateContract) -> None:
        self._repository.insert(conn, contract)
