from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.orchestration_gate_record import OrchestrationGateRecordContract
from app.domain.contracts.orchestration_gate_run import (
    OrchestrationGateRunCloseContract,
    OrchestrationGateRunOpenContract,
)
from app.domain.contracts.orchestration_packet import OrchestrationPacketContract
from app.repositories.advisory_resolution_records_repository import AdvisoryResolutionRecordsRepository
from app.repositories.command_intent_records_repository import CommandIntentRecordsRepository
from app.repositories.command_intent_runs_repository import CommandIntentRunsRepository
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.orchestration_gate_records_repository import OrchestrationGateRecordsRepository
from app.repositories.orchestration_gate_runs_repository import OrchestrationGateRunsRepository
from app.repositories.orchestration_packets_repository import OrchestrationPacketsRepository

logger = logging.getLogger(__name__)

ORCHESTRATION_VERSION = "phase9a-controlled-orchestration-gate-v1"
MAX_ACTIONS_PER_RUN = 3
COOLDOWN_MINUTES = 60
PRIORITY_ORDER = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
MEANINGFUL_COMMANDS = {
    "REDUCE_POSITION",
    "PREPARE_POSITION_EXIT",
    "EXIT_POSITION",
    "CANCEL_PENDING_ORDER",
    "BLOCK_NEW_ENTRY",
}


@dataclass(slots=True)
class OrchestrationGateRunResult:
    orchestration_gate_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class ControlledOrchestrationGateService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        orchestration_version: str = ORCHESTRATION_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._orchestration_version = orchestration_version
        self._runs = OrchestrationGateRunsRepository()
        self._records = OrchestrationGateRecordsRepository()
        self._packets = OrchestrationPacketsRepository()
        self._command_intent_runs = CommandIntentRunsRepository()
        self._command_intent_records = CommandIntentRecordsRepository()
        self._resolution_records = AdvisoryResolutionRecordsRepository()
        self._exit_advisories = ExitAdvisoryRecordsRepository()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def generate_for_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> OrchestrationGateRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for market_id in [str(market_id) for market_id in market_ids]:
                command_intents = self._command_intent_records.list_for_market(conn, market_id)
                if not command_intents:
                    raise ValueError(f"missing command intent records for market: {market_id}")
                latest_run_id = str(command_intents[0]["command_intent_run_id"])
                scoped = [dict(row) for row in command_intents if str(row["command_intent_run_id"]) == latest_run_id]
                inputs.extend(scoped)
        return self._generate(inputs, source_type=source_type, source_ref=source_ref)

    def generate_for_command_intent_run(
        self,
        command_intent_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> OrchestrationGateRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            run = self._command_intent_runs.get_by_id(conn, command_intent_run_id)
            if run is None:
                raise ValueError(f"unknown command_intent_run_id: {command_intent_run_id}")
            inputs = [dict(row) for row in self._command_intent_records.list_for_run(conn, command_intent_run_id)]
        return self._generate(inputs, source_type="command_intent_run", source_ref=source_ref or command_intent_run_id)

    def generate_for_command_intent_records(
        self,
        command_intent_record_ids: list[str],
        *,
        source_ref: str | None = None,
    ) -> OrchestrationGateRunResult | None:
        if not self.enabled:
            return None
        if not command_intent_record_ids:
            raise ValueError("at least one command_intent_record_id is required")

        inputs: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for command_intent_record_id in command_intent_record_ids:
                row = self._command_intent_records.get_by_id(conn, str(command_intent_record_id))
                if row is None:
                    raise ValueError(f"unknown command_intent_record_id: {command_intent_record_id}")
                inputs.append(dict(row))
        return self._generate(inputs, source_type="command_intent_record_batch", source_ref=source_ref)

    def _generate(
        self,
        inputs: list[dict[str, object]],
        *,
        source_type: str,
        source_ref: str | None,
    ) -> OrchestrationGateRunResult:
        run_id = str(uuid4())
        packet_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._runs.open_run(
                    conn,
                    OrchestrationGateRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        orchestration_version=self._orchestration_version,
                        started_at=started_at,
                        input_count=len(inputs),
                        metadata_json={
                            "orchestration_version": self._orchestration_version,
                            "source_ref": _optional_str(source_ref),
                            "gate_model": "controlled_orchestration_gate_v1",
                        },
                    ),
                )
                opened_run = True

                sorted_inputs = sorted(inputs, key=_command_intent_sort_key, reverse=True)
                gate_rows: list[dict[str, object]] = []
                allowed_rows: list[dict[str, object]] = []
                seen_duplicates: set[tuple[str, str, str]] = set()
                seen_conflicts: dict[tuple[str, str], str] = {}
                allow_count = 0
                cutoff = started_at - timedelta(minutes=COOLDOWN_MINUTES)

                for row in sorted_inputs:
                    try:
                        resolution = None
                        if row.get("advisory_resolution_record_id") is not None:
                            resolution = self._resolution_records.get_by_id(conn, str(row["advisory_resolution_record_id"]))
                        exit_advisory = None
                        if row.get("exit_advisory_record_id") is not None:
                            exit_advisory = self._exit_advisories.get_by_id(conn, str(row["exit_advisory_record_id"]))

                        decision = _evaluate_gate_decision(
                            command_intent=dict(row),
                            resolution_record=dict(resolution) if resolution is not None else None,
                            exit_advisory=dict(exit_advisory) if exit_advisory is not None else None,
                            seen_duplicates=seen_duplicates,
                            seen_conflicts=seen_conflicts,
                            allow_count=allow_count,
                            max_actions_per_run=MAX_ACTIONS_PER_RUN,
                            records_repo=self._records,
                            conn=conn,
                            cooldown_cutoff=cutoff,
                            packet_candidate_id=packet_id,
                        )
                        gate_rows.append(decision)
                        self._records.insert(
                            conn,
                            OrchestrationGateRecordContract(
                                id=str(uuid4()),
                                orchestration_gate_run_id=run_id,
                                market_id=str(row["market_id"]),
                                command_intent_record_id=str(row["id"]),
                                orchestration_decision_class=str(decision["orchestration_decision_class"]),
                                orchestration_reason_codes_json=list(decision["reason_codes"]),
                                orchestration_reason_text=str(decision["reason_text"]),
                                gate_explanation_json=dict(decision["explanation"]),
                                packet_candidate_id=decision["packet_candidate_id"],
                                orchestration_version=self._orchestration_version,
                            ),
                        )
                        if decision["orchestration_decision_class"] == "ALLOW_DRY_RUN":
                            allow_count += 1
                            allowed_rows.append(dict(row))
                            seen_duplicates.add((
                                str(row["exposure_type"]),
                                str(row["exposure_ref_id"]),
                                str(row["command_intent_class"]),
                            ))
                            seen_conflicts.setdefault(
                                (str(row["exposure_type"]), str(row["exposure_ref_id"])),
                                str(row["command_intent_class"]),
                            )
                        elif decision["orchestration_decision_class"] not in {"DEFER", "BLOCK"}:
                            seen_duplicates.add((
                                str(row["exposure_type"]),
                                str(row["exposure_ref_id"]),
                                str(row["command_intent_class"]),
                            ))
                            seen_conflicts.setdefault(
                                (str(row["exposure_type"]), str(row["exposure_ref_id"])),
                                str(row["command_intent_class"]),
                            )
                        success_count += 1
                    except Exception:
                        logger.exception("orchestration_gate_command_failed command_intent_record_id=%s", row["id"])
                        failure_count += 1

                packet = _build_packet(
                    packet_id=packet_id,
                    run_id=run_id,
                    allowed_rows=allowed_rows,
                    gate_rows=gate_rows,
                    orchestration_version=self._orchestration_version,
                )
                self._packets.insert(
                    conn,
                    OrchestrationPacketContract(
                        id=packet_id,
                        orchestration_gate_run_id=run_id,
                        packet_status_class=str(packet["packet_status_class"]),
                        packet_priority_class=str(packet["packet_priority_class"]),
                        packet_action_count=int(packet["packet_action_count"]),
                        markets_covered_count=int(packet["markets_covered_count"]),
                        included_command_intent_ids_json=list(packet["included_command_intent_ids_json"]),
                        packet_reason_codes_json=list(packet["packet_reason_codes_json"]),
                        packet_reason_text=str(packet["packet_reason_text"]),
                        explanation_json=dict(packet["explanation_json"]),
                        orchestration_version=self._orchestration_version,
                    ),
                )

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._runs.close_run(
                    conn,
                    OrchestrationGateRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "orchestration_version": self._orchestration_version,
                            "source_ref": _optional_str(source_ref),
                            "gate_model": "controlled_orchestration_gate_v1",
                            "packet_status_class": str(packet["packet_status_class"]),
                        },
                    ),
                )

            return OrchestrationGateRunResult(
                orchestration_gate_run_id=run_id,
                status=status,
                input_count=len(inputs),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("orchestration_gate_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._runs.open_run(
                        conn,
                        OrchestrationGateRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            orchestration_version=self._orchestration_version,
                            started_at=started_at,
                            input_count=len(inputs),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._runs.close_run(
                    conn,
                    OrchestrationGateRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(inputs)),
                        metadata_json={"error": str(exc), "orchestration_version": self._orchestration_version},
                    ),
                )
            return OrchestrationGateRunResult(
                orchestration_gate_run_id=run_id,
                status="FAILED",
                input_count=len(inputs),
                success_count=success_count,
                failure_count=max(1, len(inputs)),
            )


def _evaluate_gate_decision(
    *,
    command_intent: dict[str, object],
    resolution_record: dict[str, object] | None,
    exit_advisory: dict[str, object] | None,
    seen_duplicates: set[tuple[str, str, str]],
    seen_conflicts: dict[tuple[str, str], str],
    allow_count: int,
    max_actions_per_run: int,
    records_repo: OrchestrationGateRecordsRepository,
    conn,  # noqa: ANN001
    cooldown_cutoff: datetime,
    packet_candidate_id: str,
) -> dict[str, object]:
    exposure_key = (str(command_intent["exposure_type"]), str(command_intent["exposure_ref_id"]))
    duplicate_key = (str(command_intent["exposure_type"]), str(command_intent["exposure_ref_id"]), str(command_intent["command_intent_class"]))

    if str(command_intent["command_status_class"]) != "STAGED":
        decision = "BLOCK"
        reason_codes = ["command_status_not_staged"]
        packet_id = None
    elif str(command_intent["orchestration_eligibility_class"]) == "INELIGIBLE":
        decision = "BLOCK"
        reason_codes = ["command_intent_ineligible"]
        packet_id = None
    elif str(command_intent["orchestration_eligibility_class"]) == "REVIEW_REQUIRED":
        decision = "DEFER"
        reason_codes = ["review_required"]
        packet_id = None
    elif str(command_intent["command_intent_class"]) not in MEANINGFUL_COMMANDS:
        decision = "BLOCK"
        reason_codes = ["non_material_command_intent"]
        packet_id = None
    elif duplicate_key in seen_duplicates:
        decision = "SUPPRESS_DUPLICATE"
        reason_codes = ["duplicate_command_target"]
        packet_id = None
    elif exposure_key in seen_conflicts and seen_conflicts[exposure_key] != str(command_intent["command_intent_class"]):
        decision = "SUPPRESS_CONFLICT"
        reason_codes = ["conflicting_command_for_exposure"]
        packet_id = None
    elif records_repo.has_recent_allowed_for_exposure_command(
        conn,
        exposure_type=str(command_intent["exposure_type"]),
        exposure_ref_id=str(command_intent["exposure_ref_id"]),
        command_intent_class=str(command_intent["command_intent_class"]),
        since=cooldown_cutoff,
    ):
        decision = "DEFER"
        reason_codes = ["cooldown_active"]
        packet_id = None
    elif allow_count >= max_actions_per_run:
        decision = "DEFER"
        reason_codes = ["max_actions_per_run_reached"]
        packet_id = None
    else:
        decision = "ALLOW_DRY_RUN"
        reason_codes = ["eligible_for_dry_run_packet"]
        packet_id = packet_candidate_id

    explanation = {
        "command_intent": {
            "id": str(command_intent["id"]),
            "market_id": str(command_intent["market_id"]),
            "command_intent_class": str(command_intent["command_intent_class"]),
            "command_priority_class": str(command_intent["command_priority_class"]),
            "command_status_class": str(command_intent["command_status_class"]),
            "orchestration_eligibility_class": str(command_intent["orchestration_eligibility_class"]),
            "exposure_type": str(command_intent["exposure_type"]),
            "exposure_ref_id": str(command_intent["exposure_ref_id"]),
        },
        "resolution_record": {
            "id": _optional_str(resolution_record.get("id")) if resolution_record is not None else None,
            "action_readiness_class": _optional_str(resolution_record.get("action_readiness_class")) if resolution_record is not None else None,
            "conflict_status_class": _optional_str(resolution_record.get("conflict_status_class")) if resolution_record is not None else None,
        },
        "exit_advisory": {
            "id": _optional_str(exit_advisory.get("id")) if exit_advisory is not None else None,
            "advisory_action_class": _optional_str(exit_advisory.get("advisory_action_class")) if exit_advisory is not None else None,
        },
        "gate_output": {
            "orchestration_decision_class": decision,
            "packet_candidate_id": packet_id,
        },
    }
    return {
        "orchestration_decision_class": decision,
        "reason_codes": sorted(set(reason_codes + [
            f"command_priority_{str(command_intent['command_priority_class']).lower()}",
            f"command_intent_{str(command_intent['command_intent_class']).lower()}",
        ])),
        "reason_text": _gate_reason_text(decision),
        "packet_candidate_id": packet_id,
        "explanation": explanation,
    }


def _build_packet(
    *,
    packet_id: str,
    run_id: str,
    allowed_rows: list[dict[str, object]],
    gate_rows: list[dict[str, object]],
    orchestration_version: str,
) -> dict[str, object]:
    if allowed_rows:
        packet_status = "DRY_RUN_READY"
        packet_priority = max((str(row["command_priority_class"]) for row in allowed_rows), key=lambda value: PRIORITY_ORDER.get(value, 0))
        reason_codes = ["dry_run_packet_ready", f"allowed_action_count_{len(allowed_rows)}"]
    else:
        has_blocking = any(
            str(row["orchestration_decision_class"]) in {"BLOCK", "SUPPRESS_DUPLICATE", "SUPPRESS_CONFLICT"}
            for row in gate_rows
        )
        packet_status = "BLOCKED" if has_blocking else "EMPTY"
        packet_priority = "LOW"
        reason_codes = ["no_allowed_dry_run_actions", f"packet_status_{packet_status.lower()}"]

    included_ids = [str(row["id"]) for row in allowed_rows]
    markets = sorted({str(row["market_id"]) for row in allowed_rows})
    explanation = {
        "included_command_intents": included_ids,
        "markets": markets,
        "gate_decision_counts": _decision_counts(gate_rows),
    }
    return {
        "id": packet_id,
        "orchestration_gate_run_id": run_id,
        "packet_status_class": packet_status,
        "packet_priority_class": packet_priority,
        "packet_action_count": len(allowed_rows),
        "markets_covered_count": len(markets),
        "included_command_intent_ids_json": included_ids,
        "packet_reason_codes_json": sorted(set(reason_codes)),
        "packet_reason_text": _packet_reason_text(packet_status, len(allowed_rows)),
        "explanation_json": explanation,
        "orchestration_version": orchestration_version,
    }


def _decision_counts(gate_rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in gate_rows:
        key = str(row["orchestration_decision_class"])
        counts[key] = counts.get(key, 0) + 1
    return counts


def _command_intent_sort_key(row: dict[str, object]) -> tuple[int, str, str, str, str]:
    return (
        PRIORITY_ORDER.get(str(row["command_priority_class"]), 0),
        str(row["market_id"]),
        str(row["exposure_type"]),
        str(row["exposure_ref_id"]),
        str(row["id"]),
    )


def _gate_reason_text(decision: str) -> str:
    return f"Controlled orchestration gate decided {decision} from persisted command intent inputs."


def _packet_reason_text(packet_status: str, action_count: int) -> str:
    return f"Dry-run orchestration packet resolved to {packet_status} with {action_count} allowed action candidates."


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 9A controlled orchestration gate.")
    parser.add_argument("--market-ids", nargs="*", help="Explicit market ids to evaluate.")
    parser.add_argument("--command-intent-run-id", help="Gate a specific command intent run.")
    parser.add_argument("--command-intent-record-ids", nargs="*", help="Gate explicit command intent records.")
    args = parser.parse_args(argv)

    service = ControlledOrchestrationGateService()
    if not service.enabled:
        print("controlled_orchestration_gate_disabled")
        return 0

    result: OrchestrationGateRunResult | None
    if args.market_ids:
        result = service.generate_for_markets(args.market_ids, source_type="cli_market_batch", source_ref="cli_market_batch")
    elif args.command_intent_run_id:
        result = service.generate_for_command_intent_run(args.command_intent_run_id, source_ref=args.command_intent_run_id)
    elif args.command_intent_record_ids:
        result = service.generate_for_command_intent_records(args.command_intent_record_ids, source_ref="cli_command_intent_record_batch")
    else:
        parser.error("one of --market-ids, --command-intent-run-id, or --command-intent-record-ids is required")

    if result is None:
        return 0
    print(
        "orchestration_gate_run_id={run_id} status={status} input_count={input_count} "
        "success_count={success_count} failure_count={failure_count}".format(
            run_id=result.orchestration_gate_run_id,
            status=result.status,
            input_count=result.input_count,
            success_count=result.success_count,
            failure_count=result.failure_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
