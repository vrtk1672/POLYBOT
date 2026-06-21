from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.advisory_resolution_runs_repository import AdvisoryResolutionRunsRepository
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository


class AdvisoryResolutionQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = AdvisoryResolutionRunsRepository()
        self._records = AdvisoryResolutionRecordsRepository()
        self._policy_records = InvalidationPolicyRecordsRepository()
        self._exit_advisories = ExitAdvisoryRecordsRepository()

    def get_advisory_resolution_run_summary(self, advisory_resolution_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, advisory_resolution_run_id)
            if run is None:
                return None
            rows = self._records.list_for_run(conn, advisory_resolution_run_id)

        action_counts: dict[str, int] = {}
        readiness_counts: dict[str, int] = {}
        for row in rows:
            action_key = str(row["primary_advisory_action_class"])
            readiness_key = str(row["action_readiness_class"])
            action_counts[action_key] = action_counts.get(action_key, 0) + 1
            readiness_counts[readiness_key] = readiness_counts.get(readiness_key, 0) + 1

        return {
            "run": dict(run),
            "record_count": len(rows),
            "action_counts": action_counts,
            "readiness_counts": readiness_counts,
        }

    def list_advisory_resolution_records_for_run(self, advisory_resolution_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_for_run(conn, advisory_resolution_run_id)
        return [dict(row) for row in rows]

    def get_advisory_resolution_record_details(
        self,
        *,
        advisory_resolution_record_id: str | None = None,
        market_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if advisory_resolution_record_id is not None:
                row = self._records.get_by_id(conn, advisory_resolution_record_id)
            elif market_id is not None:
                row = self._records.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("advisory_resolution_record_id or market_id is required")
        return dict(row) if row is not None else None

    def list_action_ready_records(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_action_ready(conn, limit)
        return [dict(row) for row in rows]

    def compare_advisory_resolution_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            resolution = self._records.get_latest_by_market(conn, market_id)
            policy = self._policy_records.get_latest_by_market(conn, market_id)
            exit_advisories = self._exit_advisories.list_for_market(conn, market_id)

        if resolution is None and policy is None and not exit_advisories:
            return None

        return {
            "advisory_resolution_record": dict(resolution) if resolution is not None else None,
            "invalidation_policy_record": dict(policy) if policy is not None else None,
            "exit_advisory_records": [dict(row) for row in exit_advisories],
        }
