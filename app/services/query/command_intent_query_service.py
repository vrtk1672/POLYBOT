from __future__ import annotations

from app.db.connection import DatabaseConnectionFactory
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.command_intent_records_repository import CommandIntentRecordsRepository
from app.repositories.command_intent_runs_repository import CommandIntentRunsRepository
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository


class CommandIntentQueryService:
    def __init__(self, connection_factory: DatabaseConnectionFactory | None = None) -> None:
        self._factory = connection_factory or DatabaseConnectionFactory()
        self._runs = CommandIntentRunsRepository()
        self._records = CommandIntentRecordsRepository()
        self._resolution_records = AdvisoryResolutionRecordsRepository()
        self._exit_advisories = ExitAdvisoryRecordsRepository()
        self._policy_records = InvalidationPolicyRecordsRepository()

    def get_command_intent_run_summary(self, command_intent_run_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            run = self._runs.get_by_id(conn, command_intent_run_id)
            if run is None:
                return None
            rows = self._records.list_for_run(conn, command_intent_run_id)

        command_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        eligibility_counts: dict[str, int] = {}
        for row in rows:
            command_key = str(row["command_intent_class"])
            status_key = str(row["command_status_class"])
            eligibility_key = str(row["orchestration_eligibility_class"])
            command_counts[command_key] = command_counts.get(command_key, 0) + 1
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
            eligibility_counts[eligibility_key] = eligibility_counts.get(eligibility_key, 0) + 1

        return {
            "run": dict(run),
            "record_count": len(rows),
            "command_counts": command_counts,
            "status_counts": status_counts,
            "eligibility_counts": eligibility_counts,
        }

    def list_command_intent_records_for_run(self, command_intent_run_id: str) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_for_run(conn, command_intent_run_id)
        return [dict(row) for row in rows]

    def get_command_intent_record_details(
        self,
        *,
        command_intent_record_id: str | None = None,
        market_id: str | None = None,
        exposure_type: str | None = None,
        exposure_ref_id: str | None = None,
    ) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            if command_intent_record_id is not None:
                row = self._records.get_by_id(conn, command_intent_record_id)
            elif exposure_type is not None and exposure_ref_id is not None:
                row = self._records.get_latest_for_exposure(conn, exposure_type=exposure_type, exposure_ref_id=exposure_ref_id)
            elif market_id is not None:
                row = self._records.get_latest_by_market(conn, market_id)
            else:
                raise ValueError("command_intent_record_id, market_id, or exposure_type+exposure_ref_id is required")
        return dict(row) if row is not None else None

    def list_orchestration_eligible_command_intents(self, limit: int = 10) -> list[dict[str, object]]:
        with self._factory.connect() as conn:
            rows = self._records.list_orchestration_eligible(conn, limit)
        return [dict(row) for row in rows]

    def compare_command_intent_to_upstream_context(self, market_id: str) -> dict[str, object] | None:
        with self._factory.connect() as conn:
            command_intent_rows = self._records.list_for_market(conn, market_id)
            latest_resolution = self._resolution_records.get_latest_by_market(conn, market_id)
            latest_policy = self._policy_records.get_latest_by_market(conn, market_id)
            exit_advisories = self._exit_advisories.list_for_market(conn, market_id)

        if not command_intent_rows and latest_resolution is None and latest_policy is None and not exit_advisories:
            return None

        latest_run_id = str(command_intent_rows[0]["command_intent_run_id"]) if command_intent_rows else None
        scoped_intents = [
            dict(row) for row in command_intent_rows
            if latest_run_id is None or str(row["command_intent_run_id"]) == latest_run_id
        ]
        scoped_exit_advisories = [dict(row) for row in exit_advisories]
        if latest_resolution is not None and latest_resolution.get("exit_advisory_run_id") is not None:
            scoped_exit_advisories = [
                row for row in scoped_exit_advisories
                if str(row["exit_advisory_run_id"]) == str(latest_resolution["exit_advisory_run_id"])
            ]

        return {
            "command_intent_records": scoped_intents,
            "advisory_resolution_record": dict(latest_resolution) if latest_resolution is not None else None,
            "exit_advisory_records": scoped_exit_advisories,
            "invalidation_policy_record": dict(latest_policy) if latest_policy is not None else None,
        }
