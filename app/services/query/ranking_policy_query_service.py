from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.ranking_policy_candidates_repository import RankingPolicyCandidatesRepository
from app.repositories.ranking_policy_runs_repository import RankingPolicyRunsRepository
from app.repositories.ranking_v2_candidates_repository import RankingV2CandidatesRepository


class RankingPolicyQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = RankingPolicyRunsRepository()
        self._candidates = RankingPolicyCandidatesRepository()
        self._ranking = RankingV2CandidatesRepository()

    def get_ranking_policy_run_summary(self, ranking_policy_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, ranking_policy_run_id)
            if run is None:
                return None
            rows = self._candidates.list_for_run(conn, ranking_policy_run_id)

        decision_counts: dict[str, int] = {}
        for row in rows:
            key = str(row["gate_decision_class"])
            decision_counts[key] = decision_counts.get(key, 0) + 1

        return {
            "run": dict(run),
            "candidate_count": len(rows),
            "decision_counts": decision_counts,
        }

    def list_ranking_policy_candidates_for_run(self, ranking_policy_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_for_run(conn, ranking_policy_run_id)
        return [dict(row) for row in rows]

    def get_ranking_policy_candidate_details(
        self,
        *,
        ranking_policy_candidate_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if ranking_policy_candidate_id is not None:
                row = self._candidates.get_by_id(conn, ranking_policy_candidate_id)
            elif market_id is not None:
                row = self._candidates.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("ranking_policy_candidate_id or market_id is required")
        return dict(row) if row is not None else None

    def list_selectable_candidates(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._candidates.list_selectable(conn, limit)
        return [dict(row) for row in rows]

    def compare_ranking_policy_to_ranking_v2(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            policy = self._candidates.get_latest_by_market(conn, market_id)
            ranking = self._ranking.get_latest_by_market(conn, market_id)
        if policy is None and ranking is None:
            return None
        return {
            "ranking_policy_candidate": dict(policy) if policy is not None else None,
            "ranking_v2_candidate": dict(ranking) if ranking is not None else None,
        }
