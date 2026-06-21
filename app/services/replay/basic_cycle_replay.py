from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.replay_repository import ReplayRepository


class BasicCycleReplayService:
    def __init__(
        self,
        connection_factory: DatabaseConnectionFactory | None = None,
        repository: ReplayRepository | None = None,
    ) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._repository = repository or ReplayRepository()

    def replay_cycle(self, cycle_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            bundle = self._repository.load_cycle_bundle(conn, cycle_id)
        if bundle is None:
            return None

        decisions = list(bundle["decisions"])
        selected = [row for row in decisions if bool(row["selected"])]
        skipped = [row for row in decisions if not bool(row["selected"])]
        rankings = list(bundle["ranking_snapshots"])
        markets = list(bundle["market_snapshots"])
        cycle = dict(bundle["cycle"])

        return {
            "cycle_id": str(cycle["id"]),
            "status": cycle["status"],
            "mode": cycle["mode"],
            "selected_market_id": (
                str(cycle["selected_market_id"])
                if cycle["selected_market_id"] is not None
                else None
            ),
            "market_count": len(markets),
            "ranking_count": len(rankings),
            "decision_count": len(decisions),
            "seen_market_ids": [row["market_id"] for row in markets],
            "ranked_market_ids": [row["market_id"] for row in rankings],
            "selected_decisions": [
                {
                    "market_id": row["market_id"],
                    "reason": row["reason"],
                    "decision_type": row["decision_type"],
                }
                for row in selected
            ],
            "skipped_or_blocked_decisions": [
                {
                    "market_id": row["market_id"],
                    "reason": row["reason"],
                    "decision_type": row["decision_type"],
                }
                for row in skipped
            ],
        }
