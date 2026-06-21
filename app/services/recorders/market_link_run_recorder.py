from __future__ import annotations

from app.domain.contracts.market_link_run import MarketLinkRunCloseContract, MarketLinkRunOpenContract
from app.repositories.market_link_runs_repository import MarketLinkRunsRepository


class MarketLinkRunRecorder:
    def __init__(self, repository: MarketLinkRunsRepository | None = None) -> None:
        self._repository = repository or MarketLinkRunsRepository()

    def open_run(self, conn, run: MarketLinkRunOpenContract) -> None:
        self._repository.open_run(conn, run)

    def close_run(self, conn, run: MarketLinkRunCloseContract) -> None:
        self._repository.close_run(conn, run)
