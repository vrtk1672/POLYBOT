from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.exit_advisory_record import ExitAdvisoryRecordContract
from app.domain.contracts.exit_advisory_run import (
    ExitAdvisoryRunCloseContract,
    ExitAdvisoryRunOpenContract,
)
from app.repositories.exit_advisory_records_repository import ExitAdvisoryRecordsRepository
from app.repositories.exit_advisory_runs_repository import ExitAdvisoryRunsRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.invalidation_policy_runs_repository import InvalidationPolicyRunsRepository
from app.repositories.live_orders_repository import LiveOrdersRepository
from app.repositories.paper_orders_repository import PaperOrdersRepository
from app.repositories.paper_positions_repository import PaperPositionsRepository
from app.repositories.positions_repository import PositionsRepository
from app.repositories.shadow_orders_repository import ShadowOrdersRepository
from app.repositories.shadow_positions_repository import ShadowPositionsRepository

logger = logging.getLogger(__name__)

ADVISORY_VERSION = "phase8b-exit-advisory-v1"
TERMINAL_ORDER_STATUSES = {"FILLED", "MATCHED", "CANCELED", "CANCELLED", "REJECTED", "ERROR", "EXPIRED", "BLOCKED", "BLOCKED_MIN_SIZE"}
SUPPORTED_EXPOSURE_TYPES = (
    "PAPER_POSITION",
    "PAPER_ORDER",
    "SHADOW_POSITION",
    "SHADOW_ORDER",
    "LIVE_POSITION",
    "LIVE_ORDER",
)


@dataclass(slots=True)
class ExitAdvisoryRunResult:
    exit_advisory_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class ExitAdvisoryService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        advisory_version: str = ADVISORY_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._advisory_version = advisory_version
        self._runs = ExitAdvisoryRunsRepository()
        self._records = ExitAdvisoryRecordsRepository()
        self._policy_runs = InvalidationPolicyRunsRepository()
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
    ) -> ExitAdvisoryRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        normalized_market_ids = [str(market_id) for market_id in market_ids]
        with self._factory.connect() as conn:
            policy_records: list[dict[str, object]] = []
            for market_id in normalized_market_ids:
                row = self._policy_records.get_latest_by_market(conn, market_id)
                if row is None:
                    raise ValueError(f"missing invalidation policy record for market: {market_id}")
                policy_records.append(dict(row))
        return self._generate_from_policy_records(
            policy_records,
            source_type=source_type,
            source_ref=source_ref,
        )

    def generate_for_invalidation_policy_run(
        self,
        invalidation_policy_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> ExitAdvisoryRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            run = self._policy_runs.get_by_id(conn, invalidation_policy_run_id)
            if run is None:
                raise ValueError(f"unknown invalidation_policy_run_id: {invalidation_policy_run_id}")
            policy_records = [dict(row) for row in self._policy_records.list_for_run(conn, invalidation_policy_run_id)]
        return self._generate_from_policy_records(
            policy_records,
            source_type="invalidation_policy_run",
            source_ref=source_ref or invalidation_policy_run_id,
        )

    def generate_for_policy_records(
        self,
        invalidation_policy_record_ids: list[str],
        *,
        source_ref: str | None = None,
    ) -> ExitAdvisoryRunResult | None:
        if not self.enabled:
            return None
        if not invalidation_policy_record_ids:
            raise ValueError("at least one invalidation_policy_record_id is required")

        policy_records: list[dict[str, object]] = []
        with self._factory.connect() as conn:
            for policy_record_id in invalidation_policy_record_ids:
                row = self._policy_records.get_by_id(conn, str(policy_record_id))
                if row is None:
                    raise ValueError(f"unknown invalidation_policy_record_id: {policy_record_id}")
                policy_records.append(dict(row))
        return self._generate_from_policy_records(
            policy_records,
            source_type="policy_record_batch",
            source_ref=source_ref,
        )

    def _generate_from_policy_records(
        self,
        policy_records: list[dict[str, object]],
        *,
        source_type: str,
        source_ref: str | None,
    ) -> ExitAdvisoryRunResult:
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._runs.open_run(
                    conn,
                    ExitAdvisoryRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        advisory_version=self._advisory_version,
                        started_at=started_at,
                        input_count=len(policy_records),
                        metadata_json={
                            "advisory_version": self._advisory_version,
                            "source_ref": _optional_str(source_ref),
                            "advisory_model": "exit_advisory_v1",
                        },
                    ),
                )
                opened_run = True

                for policy_record in policy_records:
                    try:
                        exposure_contexts = self._collect_exposure_contexts(conn, str(policy_record["market_id"]))
                        for exposure_type, exposure_row in exposure_contexts:
                            advisory = _translate_exit_advisory(policy_record, exposure_type, exposure_row)
                            self._records.insert(
                                conn,
                                ExitAdvisoryRecordContract(
                                    id=str(uuid4()),
                                    exit_advisory_run_id=run_id,
                                    market_id=str(policy_record["market_id"]),
                                    invalidation_policy_record_id=str(policy_record["id"]),
                                    exposure_type=exposure_type,
                                    exposure_ref_id=str(exposure_row["id"]),
                                    advisory_action_class=str(advisory["advisory_action_class"]),
                                    advisory_priority_class=str(advisory["advisory_priority_class"]),
                                    advisory_reason_codes_json=list(advisory["reason_codes"]),
                                    advisory_reason_text=str(advisory["reason_text"]),
                                    explanation_json=dict(advisory["explanation"]),
                                    advisory_version=self._advisory_version,
                                ),
                            )
                        success_count += 1
                    except Exception:
                        logger.exception(
                            "exit_advisory_policy_record_failed invalidation_policy_record_id=%s",
                            policy_record["id"],
                        )
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._runs.close_run(
                    conn,
                    ExitAdvisoryRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "advisory_version": self._advisory_version,
                            "source_ref": _optional_str(source_ref),
                            "advisory_model": "exit_advisory_v1",
                        },
                    ),
                )

            return ExitAdvisoryRunResult(
                exit_advisory_run_id=run_id,
                status=status,
                input_count=len(policy_records),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("exit_advisory_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._runs.open_run(
                        conn,
                        ExitAdvisoryRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            advisory_version=self._advisory_version,
                            started_at=started_at,
                            input_count=len(policy_records),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._runs.close_run(
                    conn,
                    ExitAdvisoryRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(policy_records)),
                        metadata_json={"error": str(exc), "advisory_version": self._advisory_version},
                    ),
                )
            return ExitAdvisoryRunResult(
                exit_advisory_run_id=run_id,
                status="FAILED",
                input_count=len(policy_records),
                success_count=success_count,
                failure_count=max(1, len(policy_records)),
            )

    def _collect_exposure_contexts(
        self,
        conn,
        market_id: str,
    ) -> list[tuple[str, dict[str, object]]]:  # noqa: ANN001
        exposure_contexts: list[tuple[str, dict[str, object]]] = []

        for row in self._paper_positions.list_for_market(conn, market_id):
            if row["closed_at"] is None:
                exposure_contexts.append(("PAPER_POSITION", dict(row)))
        for row in self._paper_orders.list_for_market(conn, market_id):
            if _is_pending_order_status(row["status"]):
                exposure_contexts.append(("PAPER_ORDER", dict(row)))
        for row in self._shadow_positions.list_for_market(conn, market_id):
            if row["closed_at"] is None:
                exposure_contexts.append(("SHADOW_POSITION", dict(row)))
        for row in self._shadow_orders.list_for_market(conn, market_id):
            if _is_pending_order_status(row["status"]):
                exposure_contexts.append(("SHADOW_ORDER", dict(row)))
        for row in self._live_positions.list_for_market(conn, market_id):
            if row["closed_at"] is None:
                exposure_contexts.append(("LIVE_POSITION", dict(row)))
        for row in self._live_orders.list_for_market(conn, market_id):
            if _is_pending_order_status(row["status"]):
                exposure_contexts.append(("LIVE_ORDER", dict(row)))

        return exposure_contexts


def _translate_exit_advisory(
    policy_record: dict[str, object],
    exposure_type: str,
    exposure_row: dict[str, object],
) -> dict[str, object]:
    exit_policy = str(policy_record["exit_policy_class"])
    invalidation_state = str(policy_record["invalidation_state_class"])
    gate_effect = str(policy_record["deployment_gate_effect"])
    is_position = exposure_type.endswith("POSITION")
    lifecycle_signal = _position_lifecycle_signal(exposure_row) if is_position else None

    reason_codes = [
        f"policy_state_{invalidation_state.lower()}",
        f"policy_exit_{exit_policy.lower()}",
        f"policy_gate_{gate_effect.lower()}",
        f"exposure_type_{exposure_type.lower()}",
    ]

    if is_position:
        if lifecycle_signal is not None:
            action = str(lifecycle_signal["action"])
            reason_codes.extend(list(lifecycle_signal["reason_codes"]))
        elif exit_policy == "EXIT_RECOMMENDED":
            action = "EXIT"
        elif exit_policy == "PREPARE_EXIT":
            action = "PREPARE_EXIT"
        elif exit_policy == "REDUCE_EXPOSURE":
            action = "REDUCE"
        elif exit_policy in {"MONITOR_CLOSELY", "BLOCK_NEW_DEPLOYMENT"}:
            action = "WATCH"
        else:
            action = "KEEP"
    else:
        status = str(exposure_row.get("status") or "").upper()
        reason_codes.append(f"order_status_{status.lower()}" if status else "order_status_unknown")
        if exit_policy == "EXIT_RECOMMENDED":
            action = "CANCEL_PENDING"
        elif exit_policy == "PREPARE_EXIT":
            action = "CANCEL_PENDING"
        elif exit_policy == "BLOCK_NEW_DEPLOYMENT":
            action = "BLOCK_NEW_ENTRY"
        elif exit_policy == "MONITOR_CLOSELY":
            action = "WATCH"
        else:
            action = "KEEP"

    if action == "EXIT":
        priority = "CRITICAL"
    elif action == "CANCEL_PENDING":
        priority = "CRITICAL" if exit_policy == "EXIT_RECOMMENDED" or gate_effect == "HARD_BLOCK" else "HIGH"
    elif action in {"REDUCE", "PREPARE_EXIT"}:
        priority = "HIGH"
    elif action == "BLOCK_NEW_ENTRY":
        priority = "HIGH" if gate_effect == "HARD_BLOCK" else "MEDIUM"
    elif action == "WATCH":
        priority = "HIGH" if gate_effect == "HARD_BLOCK" else "MEDIUM"
    else:
        priority = "LOW"

    if action == "BLOCK_NEW_ENTRY":
        reason_codes.append("pending_new_entry_blocked")
    elif action == "CANCEL_PENDING":
        reason_codes.append("pending_order_cancel_recommended")
    elif action == "EXIT":
        reason_codes.append("open_position_exit_recommended")
    elif action == "PREPARE_EXIT":
        reason_codes.append("open_position_prepare_exit")
    elif action == "REDUCE":
        reason_codes.append("open_position_reduce")
    elif action == "WATCH":
        reason_codes.append("monitor_existing_exposure")
    else:
        reason_codes.append("keep_existing_exposure")

    explanation = {
        "policy_record": {
            "id": str(policy_record["id"]),
            "market_id": str(policy_record["market_id"]),
            "invalidation_state_class": invalidation_state,
            "exit_policy_class": exit_policy,
            "deployment_gate_effect": gate_effect,
            "policy_version": _optional_str(policy_record.get("policy_version")),
        },
        "exposure_context": {
            "exposure_type": exposure_type,
            "exposure_ref_id": str(exposure_row["id"]),
            "status": _optional_str(exposure_row.get("status") or exposure_row.get("current_status")),
            "direction": _optional_str(exposure_row.get("side") or exposure_row.get("intended_outcome")),
            "size": _optional_float(exposure_row.get("size")),
            "avg_entry": _optional_float(exposure_row.get("avg_entry")),
            "mark_price": _optional_float(exposure_row.get("mark_price")),
            "unrealized": _optional_float(exposure_row.get("unrealized")),
            "notional_basis": lifecycle_signal.get("notional_basis") if lifecycle_signal is not None else None,
            "unrealized_return": lifecycle_signal.get("unrealized_return") if lifecycle_signal is not None else None,
        },
        "advisory_output": {
            "advisory_action_class": action,
            "advisory_priority_class": priority,
        },
    }

    return {
        "advisory_action_class": action,
        "advisory_priority_class": priority,
        "reason_codes": sorted(set(reason_codes)),
        "reason_text": _reason_text(action, exposure_type),
        "explanation": explanation,
    }


def _is_pending_order_status(status: object) -> bool:
    normalized = str(status).upper() if status is not None else ""
    return bool(normalized) and normalized not in TERMINAL_ORDER_STATUSES


def _position_lifecycle_signal(exposure_row: dict[str, object]) -> dict[str, object] | None:
    size = _optional_float(exposure_row.get("size")) or 0.0
    avg_entry = _optional_float(exposure_row.get("avg_entry")) or 0.0
    mark_price = _optional_float(exposure_row.get("mark_price"))
    unrealized = _optional_float(exposure_row.get("unrealized"))
    if size <= 0 or avg_entry <= 0 or mark_price is None or unrealized is None:
        return None

    notional_basis = round(size * avg_entry, 6)
    if notional_basis <= 0:
        return None
    unrealized_return = round(unrealized / notional_basis, 6)

    if unrealized_return <= -0.25:
        return {
            "action": "EXIT",
            "reason_codes": [
                "paper_lifecycle_stop_loss",
                "paper_marked_drawdown_exit",
            ],
            "notional_basis": notional_basis,
            "unrealized_return": unrealized_return,
        }
    if unrealized_return <= -0.15:
        return {
            "action": "PREPARE_EXIT",
            "reason_codes": [
                "paper_lifecycle_drawdown_prepare_exit",
            ],
            "notional_basis": notional_basis,
            "unrealized_return": unrealized_return,
        }
    if unrealized_return >= 0.20:
        return {
            "action": "REDUCE",
            "reason_codes": [
                "paper_lifecycle_take_profit_reduce",
            ],
            "notional_basis": notional_basis,
            "unrealized_return": unrealized_return,
        }
    return None


def _reason_text(advisory_action: str, exposure_type: str) -> str:
    return f"Advisory set {advisory_action} for {exposure_type} based on persisted invalidation policy and exposure context."


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8B exit advisory translation.")
    parser.add_argument("--market-ids", nargs="*", help="Explicit market ids to evaluate.")
    parser.add_argument("--invalidation-policy-run-id", help="Translate advisories from a specific invalidation policy run.")
    parser.add_argument("--invalidation-policy-record-ids", nargs="*", help="Translate advisories for explicit invalidation policy records.")
    args = parser.parse_args(argv)

    service = ExitAdvisoryService()
    if not service.enabled:
        print("exit_advisory_disabled")
        return 0

    result: ExitAdvisoryRunResult | None
    if args.market_ids:
        result = service.generate_for_markets(args.market_ids, source_type="cli_market_batch", source_ref="cli_market_batch")
    elif args.invalidation_policy_run_id:
        result = service.generate_for_invalidation_policy_run(args.invalidation_policy_run_id, source_ref=args.invalidation_policy_run_id)
    elif args.invalidation_policy_record_ids:
        result = service.generate_for_policy_records(args.invalidation_policy_record_ids, source_ref="cli_policy_record_batch")
    else:
        parser.error("one of --market-ids, --invalidation-policy-run-id, or --invalidation-policy-record-ids is required")

    if result is None:
        return 0
    print(
        "exit_advisory_run_id={run_id} status={status} input_count={input_count} "
        "success_count={success_count} failure_count={failure_count}".format(
            run_id=result.exit_advisory_run_id,
            status=result.status,
            input_count=result.input_count,
            success_count=result.success_count,
            failure_count=result.failure_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
