from __future__ import annotations

from psycopg import Connection

from app.repositories.cycle_repository import CycleRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.ranking_snapshots_repository import RankingSnapshotsRepository


class ReplayRepository:
    def __init__(self) -> None:
        self._cycles = CycleRepository()
        self._markets = MarketSnapshotsRepository()
        self._rankings = RankingSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()

    def load_cycle_bundle(self, conn: Connection, cycle_id: str) -> dict[str, object] | None:
        cycle_row = self._cycles.get_cycle(conn, cycle_id)
        if cycle_row is None:
            return None
        return {
            "cycle": cycle_row,
            "market_snapshots": self._markets.list_for_cycle(conn, cycle_id),
            "ranking_snapshots": self._rankings.list_for_cycle(conn, cycle_id),
            "decisions": self._decisions.list_for_cycle(conn, cycle_id),
        }
