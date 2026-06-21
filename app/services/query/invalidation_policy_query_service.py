from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.invalidation_policy_runs_repository import InvalidationPolicyRunsRepository
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository
from app.repositories.ranking_policy_candidates_repository import RankingPolicyCandidatesRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository


class InvalidationPolicyQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = InvalidationPolicyRunsRepository()
        self._records = InvalidationPolicyRecordsRepository()
        self._ranking_policy = RankingPolicyCandidatesRepository()
        self._cognition = CognitionSummariesRepository()
        self._reasoning = InvalidationReasoningsRepository()
        self._trade_classifications = TradeClassificationsRepository()
        self._bucket_allocations = BucketAllocationsRepository()

    def get_invalidation_policy_run_summary(self, invalidation_policy_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, invalidation_policy_run_id)
            if run is None:
                return None
            rows = self._records.list_for_run(conn, invalidation_policy_run_id)

        exit_counts: dict[str, int] = {}
        state_counts: dict[str, int] = {}
        for row in rows:
            exit_key = str(row["exit_policy_class"])
            state_key = str(row["invalidation_state_class"])
            exit_counts[exit_key] = exit_counts.get(exit_key, 0) + 1
            state_counts[state_key] = state_counts.get(state_key, 0) + 1

        return {
            "run": dict(run),
            "record_count": len(rows),
            "exit_policy_counts": exit_counts,
            "invalidation_state_counts": state_counts,
        }

    def list_invalidation_policy_records_for_run(self, invalidation_policy_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_for_run(conn, invalidation_policy_run_id)
        return [dict(row) for row in rows]

    def get_invalidation_policy_record_details(
        self,
        *,
        invalidation_policy_record_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if invalidation_policy_record_id is not None:
                row = self._records.get_by_id(conn, invalidation_policy_record_id)
            elif market_id is not None:
                row = self._records.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("invalidation_policy_record_id or market_id is required")
        return dict(row) if row is not None else None

    def list_exit_recommended_records(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_exit_recommended(conn, limit)
        return [dict(row) for row in rows]

    def compare_invalidation_policy_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            policy = self._records.get_latest_by_market(conn, market_id)
            ranking_rows = self._ranking_policy.get_latest_by_market(conn, market_id)
            cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
            reasoning_rows = self._reasoning.list_for_market(conn, market_id, 1)
            trade_classification = self._trade_classifications.get_latest_by_market(conn, market_id)
            bucket_allocation = self._bucket_allocations.get_latest_by_market(conn, market_id)
        if (
            policy is None
            and ranking_rows is None
            and not cognition_rows
            and not reasoning_rows
            and trade_classification is None
            and bucket_allocation is None
        ):
            return None
        return {
            "invalidation_policy_record": dict(policy) if policy is not None else None,
            "ranking_policy_candidate": dict(ranking_rows) if ranking_rows is not None else None,
            "cognition_summary": dict(cognition_rows[0]) if cognition_rows else None,
            "invalidation_reasoning": dict(reasoning_rows[0]) if reasoning_rows else None,
            "trade_classification": dict(trade_classification) if trade_classification is not None else None,
            "bucket_allocation": dict(bucket_allocation) if bucket_allocation is not None else None,
        }
