from __future__ import annotations

from app.domain.contracts.market_link_candidate import MarketLinkCandidateContract
from app.repositories.market_link_candidates_repository import MarketLinkCandidatesRepository


class MarketLinkCandidateRecorder:
    def __init__(self, repository: MarketLinkCandidatesRepository | None = None) -> None:
        self._repository = repository or MarketLinkCandidatesRepository()

    def record(self, conn, candidate: MarketLinkCandidateContract) -> None:
        self._repository.insert(conn, candidate)
