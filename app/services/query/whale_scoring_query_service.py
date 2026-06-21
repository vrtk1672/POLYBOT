from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository
from app.repositories.whale_scoring_runs_repository import WhaleScoringRunsRepository


class WhaleScoringQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = WhaleScoringRunsRepository()
        self._scores = WhaleMarketScoresRepository()

    def get_whale_scoring_run_summary(self, whale_scoring_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, whale_scoring_run_id)
            if run is None:
                return None
            rows = self._scores.list_for_run(conn, whale_scoring_run_id)

        average_presence = 0.0
        average_conviction = 0.0
        if rows:
            average_presence = round(sum(float(row["whale_presence_score"]) for row in rows) / len(rows), 5)
            average_conviction = round(sum(float(row["whale_conviction_score"]) for row in rows) / len(rows), 5)

        return {
            "run": dict(run),
            "score_count": len(rows),
            "average_presence_score": average_presence,
            "average_conviction_score": average_conviction,
        }

    def list_whale_market_scores_for_run(self, whale_scoring_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._scores.list_for_run(conn, whale_scoring_run_id)
        return [dict(row) for row in rows]

    def get_whale_market_score_details(
        self,
        *,
        whale_market_score_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if whale_market_score_id is not None:
                row = self._scores.get_by_id(conn, whale_market_score_id)
            elif market_id is not None:
                row = self._scores.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("whale_market_score_id or market_id is required")
        return dict(row) if row is not None else None

    def list_top_whale_scored_markets(self, limit: int = 10, order_by: str = "whale_presence_score") -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._scores.list_top_scores(conn, limit, order_by)
        return [dict(row) for row in rows]

    def compare_whale_market_score_to_underlying_wallets(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            score = self._scores.get_latest_by_market(conn, market_id)
        if score is None:
            return None
        score_dict = dict(score)
        return {
            "score": score_dict,
            "supporting_wallets": list(score_dict.get("top_supporting_wallets_json") or []),
            "category_mix": dict(score_dict.get("category_mix_json") or {}),
        }
