from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.bucket_allocation_runs_repository import BucketAllocationRunsRepository
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository


class BucketAllocationQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = BucketAllocationRunsRepository()
        self._allocations = BucketAllocationsRepository()
        self._classifications = TradeClassificationsRepository()

    def get_bucket_allocation_run_summary(self, bucket_allocation_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, bucket_allocation_run_id)
            if run is None:
                return None
            rows = self._allocations.list_for_run(conn, bucket_allocation_run_id)

        bucket_counts: dict[str, int] = {}
        deployability_counts: dict[str, int] = {}
        for row in rows:
            bucket = str(row["assigned_bucket_class"])
            deployability = str(row["deployability_class"])
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            deployability_counts[deployability] = deployability_counts.get(deployability, 0) + 1

        return {
            "run": dict(run),
            "allocation_count": len(rows),
            "bucket_counts": bucket_counts,
            "deployability_counts": deployability_counts,
        }

    def list_bucket_allocations_for_run(self, bucket_allocation_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._allocations.list_for_run(conn, bucket_allocation_run_id)
        return [dict(row) for row in rows]

    def get_bucket_allocation_details(
        self,
        *,
        bucket_allocation_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if bucket_allocation_id is not None:
                row = self._allocations.get_by_id(conn, bucket_allocation_id)
            elif market_id is not None:
                row = self._allocations.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("bucket_allocation_id or market_id is required")
        return dict(row) if row is not None else None

    def list_bucket_allocations_by_bucket(self, assigned_bucket_class: str, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._allocations.list_by_bucket(conn, assigned_bucket_class, limit)
        return [dict(row) for row in rows]

    def compare_bucket_allocation_to_trade_classification(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            allocation = self._allocations.get_latest_by_market(conn, market_id)
            classification = self._classifications.get_latest_by_market(conn, market_id)
        if allocation is None and classification is None:
            return None
        return {
            "bucket_allocation": dict(allocation) if allocation is not None else None,
            "trade_classification": dict(classification) if classification is not None else None,
        }
