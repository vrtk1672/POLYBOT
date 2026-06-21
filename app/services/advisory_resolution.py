from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.advisory_resolution_record import AdvisoryResolutionRecordContract
from app.domain.contracts.advisory_resolution_run import (
    AdvisoryResolutionRunCloseContract,
    AdvisoryResolutionRunOpenContract,
)
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.advisory_resolution_runs_repository import AdvisoryResolutionRunsRepository
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.exit_advisory_runs_repository import ExitAdvisoryRunsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository

logger = logging.getLogger(__name__)

ADVISORY_RESOLUTION_VERSION = "phase8c-advisory-resolution-v1"
ACTION_ORDER = {
    "KEEP": 1,
    "WATCH": 2,
    "BLOCK_NEW_ENTRY": 3,
    "REDUCE": 4,
    "PREPARE_EXIT": 5,
    "CANCEL_PENDING": 6,
    "EXIT": 7,
}
POSITION_ACTIONS = {"REDUCE", "PREPARE_EXIT", "EXIT"}
PENDING_ACTIONS = {"BLOCK_NEW_ENTRY", "CANCEL_PENDING"}
UNWIND_ACTIONS = {"REDUCE", "PREPARE_EXIT", "EXIT", "CANCEL_PENDING"}


@dataclass(slots=True)
class AdvisoryResolutionRunResult:
    advisory_resolution_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class AdvisoryResolutionService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        advisory_resolution_version: str = ADVISORY_RESOLUTION_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._advisory_resolution_version = advisory_resolution_version
        self._runs = AdvisoryResolutionRunsRepository()
        self._records = AdvisoryResolutionRecordsRepository()
        self._policy_records = InvalidationPolicyRecordsRepository()
        self._exit_advisory_runs = ExitAdvisoryRunsRepository()
        self._exit_advisories = ExitAdvisoryRecordsRepository()
        self._market_snapshots = MarketSnapshotsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def generate_for_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> AdvisoryResolutionRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for market_id in [str(market_id) for market_id in market_ids]:
                policy_record = self._policy_records.get_latest_by_market(conn, market_id)
                advisory_rows = self._exit_advisories.list_for_market(conn, market_id)
                latest_advisory_run_id = str(advisory_rows[0]["exit_advisory_run_id"]) if advisory_rows else None
                scoped_advisories = [
                    dict(row) for row in advisory_rows
                    if latest_advisory_run_id is None or str(row["exit_advisory_run_id"]) == latest_advisory_run_id
                ]
                if policy_record is None and not scoped_advisories:
                    raise ValueError(f"missing policy/advisory context for market: {market_id}")
                inputs.append(
                    {
                        "market_id": market_id,
                        "policy_record": dict(policy_record) if policy_record is not None else None,
                        "exit_advisories": scoped_advisories,
                        "exit_advisory_run_id": latest_advisory_run_id,
                    }
                )
        return self._generate(inputs, source_type=source_type, source_ref=source_ref)

    def generate_for_exit_advisory_run(
        self,
        exit_advisory_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> AdvisoryResolutionRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            run = self._exit_advisory_runs.get_by_id(conn, exit_advisory_run_id)
            if run is None:
                raise ValueError(f"unknown exit_advisory_run_id: {exit_advisory_run_id}")
            advisory_rows = [dict(row) for row in self._exit_advisories.list_for_run(conn, exit_advisory_run_id)]

            grouped: dict[str, list[dict[str, object]]] = {}
            for row in advisory_rows:
                grouped.setdefault(str(row["market_id"]), []).append(row)

            inputs: list[dict[str, object]] = []
            for market_id, rows in grouped.items():
                policy_record = None
                policy_record_id = rows[0].get("invalidation_policy_record_id")
                if policy_record_id is not None:
                    policy_record = self._policy_records.get_by_id(conn, str(policy_record_id))
                inputs.append(
                    {
                        "market_id": market_id,
                        "policy_record": dict(policy_record) if policy_record is not None else None,
                        "exit_advisories": rows,
                        "exit_advisory_run_id": exit_advisory_run_id,
                    }
                )
        return self._generate(
            inputs,
            source_type="exit_advisory_run",
            source_ref=source_ref or exit_advisory_run_id,
        )

    def generate_for_policy_records(
        self,
        invalidation_policy_record_ids: list[str],
        *,
        source_ref: str | None = None,
    ) -> AdvisoryResolutionRunResult | None:
        if not self.enabled:
            return None
        if not invalidation_policy_record_ids:
            raise ValueError("at least one invalidation_policy_record_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for policy_record_id in invalidation_policy_record_ids:
                policy_record = self._policy_records.get_by_id(conn, str(policy_record_id))
                if policy_record is None:
                    raise ValueError(f"unknown invalidation_policy_record_id: {policy_record_id}")
                advisories = [dict(row) for row in self._exit_advisories.list_for_policy_record(conn, str(policy_record_id))]
                exit_advisory_run_id = str(advisories[0]["exit_advisory_run_id"]) if advisories else None
                if exit_advisory_run_id is not None:
                    advisories = [row for row in advisories if str(row["exit_advisory_run_id"]) == exit_advisory_run_id]
                inputs.append(
                    {
                        "market_id": str(policy_record["market_id"]),
                        "policy_record": dict(policy_record),
                        "exit_advisories": advisories,
                        "exit_advisory_run_id": exit_advisory_run_id,
                    }
                )
        return self._generate(
            inputs,
            source_type="policy_record_batch",
            source_ref=source_ref,
        )

    def _generate(
        self,
        inputs: list[dict[str, object]],
        *,
        source_type: str,
        source_ref: str | None,
    ) -> AdvisoryResolutionRunResult:
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._runs.open_run(
                    conn,
                    AdvisoryResolutionRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        advisory_resolution_version=self._advisory_resolution_version,
                        started_at=started_at,
                        input_count=len(inputs),
                        metadata_json={
                            "advisory_resolution_version": self._advisory_resolution_version,
                            "source_ref": _optional_str(source_ref),
                            "resolution_model": "advisory_resolution_v1",
                        },
                    ),
                )
                opened_run = True

                for item in inputs:
                    try:
                        market_id = str(item["market_id"])
                        policy_record = item["policy_record"]
                        exit_advisories = list(item["exit_advisories"])
                        exit_advisory_run_id = _optional_str(item["exit_advisory_run_id"])
                        latest_market = self._market_snapshots.get_latest_for_market(conn, market_id)
                        cycle_id = (
                            _optional_str(policy_record.get("cycle_id"))
                            if policy_record is not None and policy_record.get("cycle_id") is not None
                            else _optional_str(latest_market.get("cycle_id")) if latest_market is not None and latest_market.get("cycle_id") is not None else None
                        )

                        resolved = _resolve_market_advisories(policy_record, exit_advisories)
                        self._records.insert(
                            conn,
                            AdvisoryResolutionRecordContract(
                                id=str(uuid4()),
                                advisory_resolution_run_id=run_id,
                                market_id=market_id,
                                cycle_id=cycle_id,
                                invalidation_policy_record_id=_optional_str(policy_record.get("id")) if policy_record is not None else None,
                                exit_advisory_run_id=exit_advisory_run_id,
                                primary_advisory_action_class=str(resolved["primary_advisory_action_class"]),
                                primary_priority_class=str(resolved["primary_priority_class"]),
                                action_readiness_class=str(resolved["action_readiness_class"]),
                                conflict_status_class=str(resolved["conflict_status_class"]),
                                exposure_count=int(resolved["exposure_count"]),
                                critical_exposure_count=int(resolved["critical_exposure_count"]),
                                advisory_reason_codes_json=list(resolved["reason_codes"]),
                                advisory_reason_text=str(resolved["reason_text"]),
                                explanation_json=dict(resolved["explanation"]),
                                advisory_resolution_version=self._advisory_resolution_version,
                            ),
                        )
                        success_count += 1
                    except Exception:
                        logger.exception("advisory_resolution_market_failed market_id=%s", item["market_id"])
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._runs.close_run(
                    conn,
                    AdvisoryResolutionRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "advisory_resolution_version": self._advisory_resolution_version,
                            "source_ref": _optional_str(source_ref),
                            "resolution_model": "advisory_resolution_v1",
                        },
                    ),
                )

            return AdvisoryResolutionRunResult(
                advisory_resolution_run_id=run_id,
                status=status,
                input_count=len(inputs),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("advisory_resolution_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._runs.open_run(
                        conn,
                        AdvisoryResolutionRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            advisory_resolution_version=self._advisory_resolution_version,
                            started_at=started_at,
                            input_count=len(inputs),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._runs.close_run(
                    conn,
                    AdvisoryResolutionRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(inputs)),
                        metadata_json={"error": str(exc), "advisory_resolution_version": self._advisory_resolution_version},
                    ),
                )
            return AdvisoryResolutionRunResult(
                advisory_resolution_run_id=run_id,
                status="FAILED",
                input_count=len(inputs),
                success_count=success_count,
                failure_count=max(1, len(inputs)),
            )


def _resolve_market_advisories(
    policy_record: dict[str, object] | None,
    exit_advisories: list[dict[str, object]],
) -> dict[str, object]:
    exposure_count = len(exit_advisories)
    critical_exposure_count = sum(1 for row in exit_advisories if str(row["advisory_priority_class"]) == "CRITICAL")
    policy_gate = _optional_str(policy_record.get("deployment_gate_effect")) if policy_record is not None else None

    if not exit_advisories:
        primary_action = "NO_ACTION"
        primary_priority = "LOW"
        readiness = "NOT_READY"
        conflict_status = "NONE"
        reason_codes = ["no_exit_advisories_available"]
    else:
        actions = [str(row["advisory_action_class"]) for row in exit_advisories]
        unique_actions = set(actions)
        significant_actions = {action for action in unique_actions if action != "KEEP"}

        if not significant_actions:
            primary_action = "KEEP"
            conflict_status = "NONE" if len(unique_actions) == 1 else "MINOR_CONFLICT"
        elif _has_material_conflict(significant_actions):
            primary_action = "MIXED_ACTIONS"
            conflict_status = "MATERIAL_CONFLICT"
        else:
            primary_action = _resolve_primary_action(significant_actions)
            conflict_status = "NONE" if len(significant_actions) == 1 else "MINOR_CONFLICT"

        primary_priority = _resolve_priority(primary_action, critical_exposure_count, exit_advisories)
        readiness = _resolve_readiness(
            primary_action=primary_action,
            primary_priority=primary_priority,
            conflict_status=conflict_status,
            exposure_count=exposure_count,
            critical_exposure_count=critical_exposure_count,
            policy_record=policy_record,
            exit_advisories=exit_advisories,
        )

        reason_codes = [
            f"primary_action_{primary_action.lower()}",
            f"conflict_status_{conflict_status.lower()}",
            f"readiness_{readiness.lower()}",
            f"exposure_count_{exposure_count}",
        ]
        if critical_exposure_count:
            reason_codes.append(f"critical_exposure_count_{critical_exposure_count}")
        if policy_gate is not None:
            reason_codes.append(f"policy_gate_{policy_gate.lower()}")

    explanation = {
        "policy_record": {
            "id": _optional_str(policy_record.get("id")) if policy_record is not None else None,
            "market_id": _optional_str(policy_record.get("market_id")) if policy_record is not None else None,
            "deployment_gate_effect": _optional_str(policy_record.get("deployment_gate_effect")) if policy_record is not None else None,
            "invalidation_state_class": _optional_str(policy_record.get("invalidation_state_class")) if policy_record is not None else None,
            "exit_policy_class": _optional_str(policy_record.get("exit_policy_class")) if policy_record is not None else None,
        },
        "advisories": {
            "exposure_count": exposure_count,
            "critical_exposure_count": critical_exposure_count,
            "actions": [str(row["advisory_action_class"]) for row in exit_advisories],
            "priorities": [str(row["advisory_priority_class"]) for row in exit_advisories],
            "exit_advisory_record_ids": [str(row["id"]) for row in exit_advisories],
            "exit_advisory_run_ids": sorted({str(row["exit_advisory_run_id"]) for row in exit_advisories}) if exit_advisories else [],
        },
        "resolution": {
            "primary_advisory_action_class": primary_action,
            "primary_priority_class": primary_priority,
            "action_readiness_class": readiness,
            "conflict_status_class": conflict_status,
        },
    }

    return {
        "primary_advisory_action_class": primary_action,
        "primary_priority_class": primary_priority,
        "action_readiness_class": readiness,
        "conflict_status_class": conflict_status,
        "exposure_count": exposure_count,
        "critical_exposure_count": critical_exposure_count,
        "reason_codes": sorted(set(reason_codes)),
        "reason_text": _reason_text(primary_action, readiness, conflict_status),
        "explanation": explanation,
    }


def _has_material_conflict(actions: set[str]) -> bool:
    return "BLOCK_NEW_ENTRY" in actions and bool(actions & UNWIND_ACTIONS)


def _resolve_primary_action(actions: set[str]) -> str:
    if "EXIT" in actions:
        return "EXIT"
    if "PREPARE_EXIT" in actions:
        return "PREPARE_EXIT"
    if "REDUCE" in actions:
        return "REDUCE"
    if "CANCEL_PENDING" in actions:
        return "CANCEL_PENDING"
    if "BLOCK_NEW_ENTRY" in actions:
        return "BLOCK_NEW_ENTRY"
    if "WATCH" in actions:
        return "WATCH"
    return max(actions, key=lambda action: ACTION_ORDER.get(action, 0))


def _resolve_priority(
    primary_action: str,
    critical_exposure_count: int,
    exit_advisories: list[dict[str, object]],
) -> str:
    if primary_action in {"NO_ACTION", "KEEP"}:
        return "LOW"
    if primary_action == "WATCH":
        return "MEDIUM"
    if primary_action in {"REDUCE", "PREPARE_EXIT"}:
        return "HIGH"
    if primary_action in {"EXIT", "CANCEL_PENDING"}:
        return "CRITICAL" if critical_exposure_count > 0 else "HIGH"
    if primary_action == "BLOCK_NEW_ENTRY":
        return "HIGH" if critical_exposure_count > 0 else "MEDIUM"
    if primary_action == "MIXED_ACTIONS":
        if critical_exposure_count > 0:
            return "CRITICAL"
        if any(str(row["advisory_priority_class"]) == "HIGH" for row in exit_advisories):
            return "HIGH"
        return "MEDIUM"
    return "LOW"


def _resolve_readiness(
    *,
    primary_action: str,
    primary_priority: str,
    conflict_status: str,
    exposure_count: int,
    critical_exposure_count: int,
    policy_record: dict[str, object] | None,
    exit_advisories: list[dict[str, object]],
) -> str:
    if exposure_count == 0:
        return "NOT_READY"
    if conflict_status == "MATERIAL_CONFLICT":
        return "NOT_READY"
    if primary_action in {"NO_ACTION", "KEEP"}:
        return "NOT_READY"
    if (
        primary_action in {"EXIT", "CANCEL_PENDING"}
        and critical_exposure_count > 0
        and policy_record is not None
        and exit_advisories
    ):
        return "READY_FOR_CONTROLLED_ORCHESTRATION"
    return "READY_FOR_REVIEW"


def _reason_text(primary_action: str, readiness: str, conflict_status: str) -> str:
    return (
        f"Resolution selected {primary_action} with {readiness} readiness and "
        f"{conflict_status} conflict status from persisted advisory inputs."
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8C advisory resolution.")
    parser.add_argument("--market-ids", nargs="*", help="Explicit market ids to resolve.")
    parser.add_argument("--exit-advisory-run-id", help="Resolve final advisories from a specific exit advisory run.")
    parser.add_argument("--invalidation-policy-record-ids", nargs="*", help="Resolve final advisories for explicit invalidation policy records.")
    args = parser.parse_args(argv)

    service = AdvisoryResolutionService()
    if not service.enabled:
        print("advisory_resolution_disabled")
        return 0

    result: AdvisoryResolutionRunResult | None
    if args.market_ids:
        result = service.generate_for_markets(args.market_ids, source_type="cli_market_batch", source_ref="cli_market_batch")
    elif args.exit_advisory_run_id:
        result = service.generate_for_exit_advisory_run(args.exit_advisory_run_id, source_ref=args.exit_advisory_run_id)
    elif args.invalidation_policy_record_ids:
        result = service.generate_for_policy_records(args.invalidation_policy_record_ids, source_ref="cli_policy_record_batch")
    else:
        parser.error("one of --market-ids, --exit-advisory-run-id, or --invalidation-policy-record-ids is required")

    if result is None:
        return 0
    print(
        "advisory_resolution_run_id={run_id} status={status} input_count={input_count} "
        "success_count={success_count} failure_count={failure_count}".format(
            run_id=result.advisory_resolution_run_id,
            status=result.status,
            input_count=result.input_count,
            success_count=result.success_count,
            failure_count=result.failure_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
