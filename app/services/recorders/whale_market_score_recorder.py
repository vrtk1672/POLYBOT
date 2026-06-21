from __future__ import annotations

from psycopg import Connection

from app.domain.contracts.whale_market_score import WhaleMarketScoreContract
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository


class WhaleMarketScoreRecorder:
    def __init__(self, repository: WhaleMarketScoresRepository | None = None) -> None:
        self._repository = repository or WhaleMarketScoresRepository()

    def record(self, conn: Connection, contract: WhaleMarketScoreContract) -> None:
        self._repository.insert(conn, contract)
