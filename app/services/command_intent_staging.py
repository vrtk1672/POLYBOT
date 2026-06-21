from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.command_intent_record import CommandIntentRecordContract
from app.domain.contracts.command_intent_run import (
    CommandIntentRunCloseContract,
    CommandIntentRunOpenContract,
)
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.advisory_resolution_runs_repository import AdvisoryResolutionRunsRepository
from app.repositories.command_intent_records_repository import CommandIntentRecordsRepository
from app.repositories.command_intent_runs_repository import CommandIntentRunsRepository
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.live_orders_repository import LiveOrdersRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.repositories.positions_repository import PositionsRepository
from app.repositories.shadow_orders_repository import ShadowOrdersRepository
from app.repositories.shadow_positions_repository import ShadowPositionsRepository

logger = logging.getLogger(__name__)

COMMAND_INTENT_VERSION = "phase8d-command-intent-v1"
TERMINAL_ORDER_STATUSES = {"FILLED", "MATCHED", "CANCELED", "CANCELLED", "REJECTED", "ERROR", "EXPIRED", "BLOCKED", "BLOCKED_MIN_SIZE"}
SUPPORTED_EXPOSURE_TYPES = {
    "PAPER_POSITION",
    "PAPER_ORDER",
    "SHADOW_POSITION",
    "SHADOW_ORDER",
    "LIVE_POSITION",
    "LIVE_ORDER",
}
POSITION_EXPOSURE_TYPES = {"PAPER_POSITION", "SHADOW_POSITION", "LIVE_POSITION"}
ORDER_EXPOSURE_TYPES = {"PAPER_ORDER", "SHADOW_ORDER", "LIVE_ORDER"}
MEANINGFUL_COMMANDS = {
    "REDUCE_POSITION",
    "PREPARE_POSITION_EXIT",
    "EXIT_POSITION",
    "CANCEL_PENDING_ORDER",
    "BLOCK_NEW_ENTRY",
}


@dataclass(slots=True)
class CommandIntentRunResult:
    command_intent_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class CommandIntentStagingService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        command_intent_version: str = COMMAND_INTENT_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._command_intent_version = command_intent_version
        self._runs = CommandIntentRunsRepository()
        self._records = CommandIntentRecordsRepository()
        self._resolution_runs = AdvisoryResolutionRunsRepository()
        self._resolution_records = AdvisoryResolutionRecordsRepository()
        self._exit_advisories = ExitAdvisoryRecordsRepository()
        self._policy_records = InvalidationPolicyRecordsRepository()
        self._paper_positions = PaperPositionsRepository()
        self._paper_orders = PaperOrdersRepository()
        self._shadow_positions = ShadowPositionsRepository()
        self._shadow_orders = ShadowOrdersRepository()
        self._live_positions = PositionsRepository()
        self._live_orders = LiveOrdersRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def generate_for_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> CommandIntentRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for market_id in [str(market_id) for market_id in market_ids]:
                resolution = self._resolution_records.get_latest_by_market(conn, market_id)
                if resolution is None:
                    raise ValueError(f"missing advisory resolution record for market: {market_id}")
                scoped_advisories = _scope_exit_advisories_to_resolution(
                    self._exit_advisories.list_for_market(conn, market_id),
                    resolution,
                )
                inputs.append(
                    {
                        "market_id": market_id,
                        "resolution_record": dict(resolution),
                        "exit_advisories": scoped_advisories,
                    }
                )
        return self._generate(inputs, source_type=source_type, source_ref=source_ref)

    def generate_for_advisory_resolution_run(
        self,
        advisory_resolution_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> CommandIntentRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            run = self._resolution_runs.get_by_id(conn, advisory_resolution_run_id)
            if run is None:
                raise ValueError(f"unknown advisory_resolution_run_id: {advisory_resolution_run_id}")
            resolutions = [dict(row) for row in self._resolution_records.list_for_run(conn, advisory_resolution_run_id)]

            inputs: list[dict[str, object]] = []
            for resolution in resolutions:
                scoped_advisories = _scope_exit_advisories_to_resolution(
                    self._exit_advisories.list_for_market(conn, str(resolution["market_id"])),
                    resolution,
                )
                inputs.append(
                    {
                        "market_id": str(resolution["market_id"]),
                        "resolution_record": resolution,
                        "exit_advisories": scoped_advisories,
                    }
                )
        return self._generate(
            inputs,
            source_type="advisory_resolution_run",
            source_ref=source_ref or advisory_resolution_run_id,
        )

    def generate_for_resolution_records(
        self,
        advisory_resolution_record_ids: list[str],
        *,
        source_ref: str | None = None,
    ) -> CommandIntentRunResult | None:
        if not self.enabled:
            return None
        if not advisory_resolution_record_ids:
            raise ValueError("at least one advisory_resolution_record_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for resolution_record_id in advisory_resolution_record_ids:
                resolution = self._resolution_records.get_by_id(conn, str(resolution_record_id))
                if resolution is None:
                    raise ValueError(f"unknown advisory_resolution_record_id: {resolution_record_id}")
                scoped_advisories = _scope_exit_advisories_to_resolution(
                    self._exit_advisories.list_for_market(conn, str(resolution["market_id"])),
                    resolution,
                )
                inputs.append(
                    {
                        "market_id": str(resolution["market_id"]),
                        "resolution_record": dict(resolution),
                        "exit_advisories": scoped_advisories,
                    }
                )
        return self._generate(inputs, source_type="resolution_record_batch", source_ref=source_ref)

    def _generate(
        self,
        inputs: list[dict[str, object]],
        *,
        source_type: str,
        source_ref: str | None,
    ) -> CommandIntentRunResult:
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._runs.open_run(
                    conn,
                    CommandIntentRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        command_intent_version=self._command_intent_version,
                        started_at=started_at,
                        input_count=len(inputs),
                        metadata_json={
                            "command_intent_version": self._command_intent_version,
                            "source_ref": _optional_str(source_ref),
                            "staging_model": "command_intent_v1",
                        },
                    ),
                )
                opened_run = True

                for item in inputs:
                    try:
                        resolution_record = dict(item["resolution_record"])
                        exit_advisories = _dedupe_exit_advisories(list(item["exit_advisories"]))
                        policy_record = None
                        policy_record_id = resolution_record.get("invalidation_policy_record_id")
                        if policy_record_id is not None:
                            policy_record = self._policy_records.get_by_id(conn, str(policy_record_id))

                        for exit_advisory in exit_advisories:
                            exposure_row = self._get_exposure_row(
                                conn,
                                exposure_type=str(exit_advisory["exposure_type"]),
                                exposure_ref_id=str(exit_advisory["exposure_ref_id"]),
                            )
                            staged = _stage_command_intent(
                                resolution_record=resolution_record,
                                exit_advisory=dict(exit_advisory),
                                exposure_row=exposure_row,
                                policy_record=dict(policy_record) if policy_record is not None else None,
                            )
                            self._records.insert(
                                conn,
                                CommandIntentRecordContract(
                                    id=str(uuid4()),
                                    command_intent_run_id=run_id,
                                    market_id=str(resolution_record["market_id"]),
                                    advisory_resolution_record_id=str(resolution_record["id"]),
                                    exit_advisory_record_id=str(exit_advisory["id"]),
                                    exposure_type=str(exit_advisory["exposure_type"]),
                                    exposure_ref_id=str(exit_advisory["exposure_ref_id"]),
                                    command_intent_class=str(staged["command_intent_class"]),
                                    command_priority_class=str(staged["command_priority_class"]),
                                    command_status_class=str(staged["command_status_class"]),
                                    orchestration_eligibility_class=str(staged["orchestration_eligibility_class"]),
                                    command_reason_codes_json=list(staged["reason_codes"]),
                                    command_reason_text=str(staged["reason_text"]),
                                    explanation_json=dict(staged["explanation"]),
                                    advisory_resolution_version=_optional_str(resolution_record.get("advisory_resolution_version")),
                                    command_intent_version=self._command_intent_version,
                                ),
                            )
                        success_count += 1
                    except Exception:
                        logger.exception(
                            "command_intent_resolution_failed advisory_resolution_record_id=%s",
                            item["resolution_record"]["id"],
                        )
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._runs.close_run(
                    conn,
                    CommandIntentRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "command_intent_version": self._command_intent_version,
                            "source_ref": _optional_str(source_ref),
                            "staging_model": "command_intent_v1",
                        },
                    ),
                )

            return CommandIntentRunResult(
                command_intent_run_id=run_id,
                status=status,
                input_count=len(inputs),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("command_intent_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._runs.open_run(
                        conn,
                        CommandIntentRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            command_intent_version=self._command_intent_version,
                            started_at=started_at,
                            input_count=len(inputs),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._runs.close_run(
                    conn,
                    CommandIntentRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(inputs)),
                        metadata_json={"error": str(exc), "command_intent_version": self._command_intent_version},
                    ),
                )
            return CommandIntentRunResult(
                command_intent_run_id=run_id,
                status="FAILED",
                input_count=len(inputs),
                success_count=success_count,
                failure_count=max(1, len(inputs)),
            )

    def _get_exposure_row(
        self,
        conn,  # noqa: ANN001
        *,
        exposure_type: str,
        exposure_ref_id: str,
    ) -> dict[str, object] | None:
        if exposure_type == "PAPER_POSITION":
            row = self._paper_positions.get_by_id(conn, exposure_ref_id)
        elif exposure_type == "PAPER_ORDER":
            row = self._paper_orders.get_by_id(conn, exposure_ref_id)
        elif exposure_type == "SHADOW_POSITION":
            row = self._shadow_positions.get_by_id(conn, exposure_ref_id)
        elif exposure_type == "SHADOW_ORDER":
            row = self._shadow_orders.get_by_id(conn, exposure_ref_id)
        elif exposure_type == "LIVE_POSITION":
            row = self._live_positions.get_by_id(conn, exposure_ref_id)
        elif exposure_type == "LIVE_ORDER":
            row = self._live_orders.get_by_id(conn, exposure_ref_id)
        else:
            return None
        return dict(row) if row is not None else None


def _scope_exit_advisories_to_resolution(
    advisory_rows: list[dict[str, object]],
    resolution_record: dict[str, object],
) -> list[dict[str, object]]:
    scoped = [dict(row) for row in advisory_rows]
    exit_advisory_run_id = resolution_record.get("exit_advisory_run_id")
    if exit_advisory_run_id is not None:
        scoped = [row for row in scoped if str(row["exit_advisory_run_id"]) == str(exit_advisory_run_id)]
    return scoped


def _dedupe_exit_advisories(advisories: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for row in advisories:
        key = (str(row["exposure_type"]), str(row["exposure_ref_id"]))
        deduped.setdefault(key, dict(row))
    return list(deduped.values())


def _stage_command_intent(
    *,
    resolution_record: dict[str, object],
    exit_advisory: dict[str, object],
    exposure_row: dict[str, object] | None,
    policy_record: dict[str, object] | None,
) -> dict[str, object]:
    command_intent_class = _map_command_intent_class(resolution_record, exit_advisory)
    exposure_type = str(exit_advisory["exposure_type"])
    suppression_reasons: list[str] = []

    if exposure_type not in SUPPORTED_EXPOSURE_TYPES:
        suppression_reasons.append("unsupported_exposure_type")
    if not str(exit_advisory.get("exposure_ref_id") or ""):
        suppression_reasons.append("missing_exposure_ref")
    if exposure_row is None:
        suppression_reasons.append("missing_exposure_row")
    elif _is_irrelevant_exposure(exposure_type=exposure_type, exposure_row=exposure_row):
        suppression_reasons.append("irrelevant_or_terminal_exposure")
    if _is_unsupported_command_for_exposure(command_intent_class=command_intent_class, exposure_type=exposure_type):
        suppression_reasons.append("unsupported_command_for_exposure")

    orchestration_eligibility_class = _resolve_orchestration_eligibility(
        resolution_record=resolution_record,
        command_intent_class=command_intent_class,
        suppression_reasons=suppression_reasons,
    )
    command_status_class = _resolve_command_status(
        command_intent_class=command_intent_class,
        orchestration_eligibility_class=orchestration_eligibility_class,
        suppression_reasons=suppression_reasons,
    )
    command_priority_class = _resolve_command_priority(
        command_intent_class=command_intent_class,
        resolution_record=resolution_record,
        exit_advisory=exit_advisory,
    )

    reason_codes = [
        f"resolution_action_{str(resolution_record['primary_advisory_action_class']).lower()}",
        f"resolution_readiness_{str(resolution_record['action_readiness_class']).lower()}",
        f"resolution_conflict_{str(resolution_record['conflict_status_class']).lower()}",
        f"exit_advisory_action_{str(exit_advisory['advisory_action_class']).lower()}",
        f"command_intent_{command_intent_class.lower()}",
        f"command_status_{command_status_class.lower()}",
        f"orchestration_eligibility_{orchestration_eligibility_class.lower()}",
        f"exposure_type_{exposure_type.lower()}",
    ]
    if suppression_reasons:
        reason_codes.extend(suppression_reasons)
    if policy_record is not None and policy_record.get("deployment_gate_effect") is not None:
        reason_codes.append(f"policy_gate_{str(policy_record['deployment_gate_effect']).lower()}")

    explanation = {
        "resolution_record": {
            "id": str(resolution_record["id"]),
            "market_id": str(resolution_record["market_id"]),
            "primary_advisory_action_class": str(resolution_record["primary_advisory_action_class"]),
            "primary_priority_class": str(resolution_record["primary_priority_class"]),
            "action_readiness_class": str(resolution_record["action_readiness_class"]),
            "conflict_status_class": str(resolution_record["conflict_status_class"]),
            "advisory_resolution_version": _optional_str(resolution_record.get("advisory_resolution_version")),
        },
        "exit_advisory": {
            "id": str(exit_advisory["id"]),
            "exit_advisory_run_id": str(exit_advisory["exit_advisory_run_id"]),
            "advisory_action_class": str(exit_advisory["advisory_action_class"]),
            "advisory_priority_class": str(exit_advisory["advisory_priority_class"]),
            "exposure_type": exposure_type,
            "exposure_ref_id": str(exit_advisory["exposure_ref_id"]),
        },
        "exposure_context": {
            "exists": exposure_row is not None,
            "status": _exposure_status(exposure_row),
            "closed_at": _optional_str(exposure_row.get("closed_at")) if exposure_row is not None else None,
        },
        "policy_record": {
            "id": _optional_str(policy_record.get("id")) if policy_record is not None else None,
            "deployment_gate_effect": _optional_str(policy_record.get("deployment_gate_effect")) if policy_record is not None else None,
            "exit_policy_class": _optional_str(policy_record.get("exit_policy_class")) if policy_record is not None else None,
        },
        "command_intent_output": {
            "command_intent_class": command_intent_class,
            "command_priority_class": command_priority_class,
            "command_status_class": command_status_class,
            "orchestration_eligibility_class": orchestration_eligibility_class,
        },
    }

    return {
        "command_intent_class": command_intent_class,
        "command_priority_class": command_priority_class,
        "command_status_class": command_status_class,
        "orchestration_eligibility_class": orchestration_eligibility_class,
        "reason_codes": sorted(set(reason_codes)),
        "reason_text": _reason_text(
            command_intent_class=command_intent_class,
            command_status_class=command_status_class,
            orchestration_eligibility_class=orchestration_eligibility_class,
        ),
        "explanation": explanation,
    }


def _map_command_intent_class(
    resolution_record: dict[str, object],
    exit_advisory: dict[str, object],
) -> str:
    advisory_action = str(exit_advisory["advisory_action_class"])
    resolution_action = str(resolution_record["primary_advisory_action_class"])
    exposure_type = str(exit_advisory["exposure_type"])

    if advisory_action == "EXIT":
        return "EXIT_POSITION"
    if advisory_action == "PREPARE_EXIT":
        return "PREPARE_POSITION_EXIT"
    if advisory_action == "REDUCE":
        return "REDUCE_POSITION"
    if advisory_action == "CANCEL_PENDING":
        return "CANCEL_PENDING_ORDER"
    if advisory_action == "BLOCK_NEW_ENTRY":
        return "BLOCK_NEW_ENTRY"
    if advisory_action == "WATCH":
        return "WATCH_ONLY"
    if advisory_action == "KEEP":
        if resolution_action in {"WATCH", "MIXED_ACTIONS"} or exposure_type in ORDER_EXPOSURE_TYPES:
            return "WATCH_ONLY"
        return "NO_OP"
    return "NO_OP"


def _resolve_command_priority(
    *,
    command_intent_class: str,
    resolution_record: dict[str, object],
    exit_advisory: dict[str, object],
) -> str:
    advisory_priority = str(exit_advisory["advisory_priority_class"])
    resolution_priority = str(resolution_record["primary_priority_class"])

    if command_intent_class == "NO_OP":
        return "LOW"
    if command_intent_class == "WATCH_ONLY":
        return "MEDIUM" if advisory_priority != "LOW" or resolution_priority != "LOW" else "LOW"
    if command_intent_class in {"REDUCE_POSITION", "PREPARE_POSITION_EXIT", "BLOCK_NEW_ENTRY"}:
        return "HIGH" if advisory_priority in {"HIGH", "CRITICAL"} or resolution_priority in {"HIGH", "CRITICAL"} else "MEDIUM"
    if command_intent_class in {"EXIT_POSITION", "CANCEL_PENDING_ORDER"}:
        return "CRITICAL" if advisory_priority == "CRITICAL" or resolution_priority == "CRITICAL" else "HIGH"
    return "LOW"


def _resolve_orchestration_eligibility(
    *,
    resolution_record: dict[str, object],
    command_intent_class: str,
    suppression_reasons: list[str],
) -> str:
    if suppression_reasons:
        return "INELIGIBLE"
    if command_intent_class not in MEANINGFUL_COMMANDS:
        return "INELIGIBLE"
    if str(resolution_record["conflict_status_class"]) == "MATERIAL_CONFLICT":
        return "INELIGIBLE"

    readiness = str(resolution_record["action_readiness_class"])
    if readiness == "READY_FOR_CONTROLLED_ORCHESTRATION":
        return "ELIGIBLE_FOR_CONTROLLED_ORCHESTRATION"
    if readiness == "READY_FOR_REVIEW":
        return "REVIEW_REQUIRED"
    return "INELIGIBLE"


def _resolve_command_status(
    *,
    command_intent_class: str,
    orchestration_eligibility_class: str,
    suppression_reasons: list[str],
) -> str:
    if suppression_reasons:
        return "SUPPRESSED"
    if command_intent_class in {"NO_OP", "WATCH_ONLY"}:
        return "NOT_ELIGIBLE"
    if orchestration_eligibility_class == "INELIGIBLE":
        return "NOT_ELIGIBLE"
    return "STAGED"


def _is_unsupported_command_for_exposure(*, command_intent_class: str, exposure_type: str) -> bool:
    if command_intent_class in {"REDUCE_POSITION", "PREPARE_POSITION_EXIT", "EXIT_POSITION"}:
        return exposure_type not in POSITION_EXPOSURE_TYPES
    if command_intent_class in {"CANCEL_PENDING_ORDER", "BLOCK_NEW_ENTRY"}:
        return exposure_type not in ORDER_EXPOSURE_TYPES
    return False


def _is_irrelevant_exposure(*, exposure_type: str, exposure_row: dict[str, object]) -> bool:
    if exposure_type in POSITION_EXPOSURE_TYPES:
        if exposure_row.get("closed_at") is not None:
            return True
        status = _exposure_status(exposure_row)
        return status in {"CLOSED", "EXITED", "SETTLED"}
    status = _exposure_status(exposure_row)
    return bool(status) and status in TERMINAL_ORDER_STATUSES


def _exposure_status(exposure_row: dict[str, object] | None) -> str | None:
    if exposure_row is None:
        return None
    raw = exposure_row.get("status")
    if raw is None:
        raw = exposure_row.get("current_status")
    if raw is None:
        return None
    return str(raw).upper()


def _reason_text(
    *,
    command_intent_class: str,
    command_status_class: str,
    orchestration_eligibility_class: str,
) -> str:
    return (
        f"Command intent staged as {command_intent_class} with {command_status_class} status "
        f"and {orchestration_eligibility_class} eligibility from persisted advisory inputs."
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8D command intent staging.")
    parser.add_argument("--market-ids", nargs="*", help="Explicit market ids to stage.")
    parser.add_argument("--advisory-resolution-run-id", help="Stage intents from a specific advisory resolution run.")
    parser.add_argument("--advisory-resolution-record-ids", nargs="*", help="Stage intents for explicit advisory resolution records.")
    args = parser.parse_args(argv)

    service = CommandIntentStagingService()
    if not service.enabled:
        print("command_intent_staging_disabled")
        return 0

    result: CommandIntentRunResult | None
    if args.market_ids:
        result = service.generate_for_markets(args.market_ids, source_type="cli_market_batch", source_ref="cli_market_batch")
    elif args.advisory_resolution_run_id:
        result = service.generate_for_advisory_resolution_run(args.advisory_resolution_run_id, source_ref=args.advisory_resolution_run_id)
    elif args.advisory_resolution_record_ids:
        result = service.generate_for_resolution_records(args.advisory_resolution_record_ids, source_ref="cli_resolution_record_batch")
    else:
        parser.error("one of --market-ids, --advisory-resolution-run-id, or --advisory-resolution-record-ids is required")

    if result is None:
        return 0
    print(
        "command_intent_run_id={run_id} status={status} input_count={input_count} "
        "success_count={success_count} failure_count={failure_count}".format(
            run_id=result.command_intent_run_id,
            status=result.status,
            input_count=result.input_count,
            success_count=result.success_count,
            failure_count=result.failure_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
