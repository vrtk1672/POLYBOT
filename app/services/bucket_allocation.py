from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.bucket_allocation import BucketAllocationContract
from app.domain.contracts.bucket_allocation_run import (
    BucketAllocationRunCloseContract,
    BucketAllocationRunOpenContract,
)
from app.repositories.bucket_allocation_runs_repository import BucketAllocationRunsRepository
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.services.recorders.bucket_allocation_recorder import BucketAllocationRecorder
from app.services.recorders.bucket_allocation_run_recorder import BucketAllocationRunRecorder

logger = logging.getLogger(__name__)

ALLOCATOR_VERSION = "phase6b-bucket-allocation-v1"

BUCKET_MODEL: dict[str, dict[str, float | str]] = {
    "FAST_TRADE": {"bucket": "FAST_BUCKET", "target": 0.15, "cap": 0.25},
    "RISKY_HIGHER_UPSIDE": {"bucket": "RISKY_BUCKET", "target": 0.10, "cap": 0.15},
    "WHALE_FOLLOW": {"bucket": "WHALE_BUCKET", "target": 0.20, "cap": 0.30},
    "SLOW_CONVICTION": {"bucket": "CONVICTION_BUCKET", "target": 0.25, "cap": 0.40},
    "NO_TRADE": {"bucket": "NO_BUCKET", "target": 0.00, "cap": 0.00},
}

RISK_MULTIPLIER = {
    "LOW_RISK": 1.00,
    "BALANCED": 0.85,
    "ELEVATED_RISK": 0.65,
    "HIGH_RISK": 0.40,
    "DO_NOT_DEPLOY": 0.00,
}


@dataclass(slots=True)
class BucketAllocationRunResult:
    bucket_allocation_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class BucketAllocationService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        allocator_version: str = ALLOCATOR_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._allocator_version = allocator_version
        self._runs = BucketAllocationRunsRepository()
        self._allocations = BucketAllocationsRepository()
        self._classifications = TradeClassificationsRepository()
        self._run_recorder = BucketAllocationRunRecorder()
        self._allocation_recorder = BucketAllocationRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def allocate_classifications(
        self,
        trade_classification_ids: list[str],
        *,
        source_type: str = "trade_classification_batch",
        source_ref: str | None = None,
    ) -> BucketAllocationRunResult | None:
        if not self.enabled:
            return None
        if not trade_classification_ids:
            raise ValueError("at least one trade_classification_id is required")

        normalized_ids = [str(classification_id) for classification_id in trade_classification_ids]
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    BucketAllocationRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        allocator_version=self._allocator_version,
                        started_at=started_at,
                        input_count=len(normalized_ids),
                        metadata_json={
                            "allocator_version": self._allocator_version,
                            "source_ref": _optional_str(source_ref),
                            "occupancy_model": "run_local_bucket_occupancy_v1",
                        },
                    ),
                )
                opened_run = True

                rows: list[dict[str, object]] = []
                for classification_id in normalized_ids:
                    row = self._classifications.get_by_id(conn, classification_id)
                    if row is None:
                        logger.exception("bucket_allocation_missing_classification id=%s", classification_id)
                        failure_count += 1
                        continue
                    rows.append(dict(row))

                occupancy_totals: dict[str, float] = {}
                rows.sort(
                    key=lambda row: (
                        float(row["classification_confidence"]),
                        -1.0 if str(row["primary_trade_type"]) == "NO_TRADE" else 0.0,
                    ),
                    reverse=True,
                )

                for row in rows:
                    try:
                        allocation = self._allocate_classification(row, occupancy_totals)
                        contract = BucketAllocationContract(
                            id=str(uuid4()),
                            bucket_allocation_run_id=run_id,
                            market_id=str(row["market_id"]),
                            trade_classification_id=str(row["id"]),
                            primary_trade_type=str(row["primary_trade_type"]),
                            assigned_bucket_class=str(allocation["assigned_bucket_class"]),
                            bucket_target_fraction=float(allocation["bucket_target_fraction"]),
                            bucket_cap_fraction=float(allocation["bucket_cap_fraction"]),
                            deployment_fraction=float(allocation["deployment_fraction"]),
                            occupancy_status=str(allocation["occupancy_status"]),
                            deployability_class=str(allocation["deployability_class"]),
                            allocation_reason_codes_json=list(allocation["reason_codes"]),
                            allocation_reason_text=str(allocation["reason_text"]),
                            explanation_json=dict(allocation["explanation"]),
                            allocator_version=self._allocator_version,
                        )
                        self._allocation_recorder.record(conn, contract)
                        success_count += 1
                    except Exception:
                        logger.exception("bucket_allocation_failed market_id=%s", row["market_id"])
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    BucketAllocationRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "allocator_version": self._allocator_version,
                            "source_ref": _optional_str(source_ref),
                            "occupancy_model": "run_local_bucket_occupancy_v1",
                            "bucket_usage": occupancy_totals,
                        },
                    ),
                )

            return BucketAllocationRunResult(
                bucket_allocation_run_id=run_id,
                status=status,
                input_count=len(normalized_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("bucket_allocation_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        BucketAllocationRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            allocator_version=self._allocator_version,
                            started_at=started_at,
                            input_count=len(normalized_ids),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    BucketAllocationRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_ids)),
                        metadata_json={"error": str(exc), "allocator_version": self._allocator_version},
                    ),
                )
            return BucketAllocationRunResult(
                bucket_allocation_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_ids)),
            )

    def allocate_for_classification_run(
        self,
        trade_classification_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> BucketAllocationRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._classifications.list_for_run(conn, trade_classification_run_id)
        ids = [str(row["id"]) for row in rows]
        return self.allocate_classifications(
            ids,
            source_type="trade_classification_run",
            source_ref=source_ref or trade_classification_run_id,
        )

    def _allocate_classification(
        self,
        row: dict[str, object],
        occupancy_totals: dict[str, float],
    ) -> dict[str, object]:
        primary_trade_type = str(row["primary_trade_type"])
        model = BUCKET_MODEL.get(primary_trade_type)
        if model is None:
            raise ValueError(f"unsupported primary_trade_type: {primary_trade_type}")

        assigned_bucket = str(model["bucket"])
        target_fraction = float(model["target"])
        cap_fraction = float(model["cap"])
        confidence = _clamp(float(row["classification_confidence"]))
        risk_posture = str(row["risk_posture_class"])
        risk_multiplier = RISK_MULTIPLIER.get(risk_posture, 0.0)
        current_bucket_occupancy = occupancy_totals.get(assigned_bucket, 0.0)

        reason_codes: list[str] = [_mapping_reason(primary_trade_type)]
        if float(row["classification_confidence"]) < 0.45:
            reason_codes.append("sparse_classification_context")
        if confidence < 0.999:
            reason_codes.append("confidence_scaled_deployment")
        if risk_multiplier < 1.0:
            reason_codes.append("risk_reduced_deployment")

        base_deployment = round(target_fraction * confidence * risk_multiplier, 5)
        deployment_fraction = base_deployment
        occupancy_status = "EMPTY"
        deployability_class = "DEPLOYABLE"

        if assigned_bucket == "NO_BUCKET" or risk_posture == "DO_NOT_DEPLOY":
            deployment_fraction = 0.0
            occupancy_status = "BLOCKED"
            deployability_class = "BLOCKED"
            reason_codes.append("do_not_deploy_risk_posture" if risk_posture == "DO_NOT_DEPLOY" else "no_trade_blocked")
        elif current_bucket_occupancy <= 0:
            occupancy_status = "EMPTY"

        projected_occupancy = round(current_bucket_occupancy + deployment_fraction, 5)
        if deployability_class != "BLOCKED":
            if projected_occupancy <= target_fraction:
                occupancy_status = "EMPTY" if current_bucket_occupancy <= 0 else "AVAILABLE"
                deployability_class = "DEPLOYABLE"
                reason_codes.append("bucket_within_target")
                occupancy_totals[assigned_bucket] = projected_occupancy
            elif projected_occupancy <= cap_fraction:
                occupancy_status = "LIMITED"
                deployability_class = "LIMITED"
                remaining = max(0.0, round(cap_fraction - current_bucket_occupancy, 5))
                deployment_fraction = min(deployment_fraction, remaining)
                if deployment_fraction <= 0:
                    occupancy_status = "SATURATED"
                    deployability_class = "SATURATED"
                    reason_codes.append("bucket_cap_reached")
                else:
                    reason_codes.append("bucket_near_cap")
                    occupancy_totals[assigned_bucket] = round(current_bucket_occupancy + deployment_fraction, 5)
            else:
                deployment_fraction = 0.0
                occupancy_status = "SATURATED"
                deployability_class = "SATURATED"
                reason_codes.append("bucket_cap_reached")

        reason_text = _build_reason_text(
            bucket=assigned_bucket,
            deployment_fraction=deployment_fraction,
            occupancy_status=occupancy_status,
            deployability_class=deployability_class,
        )
        explanation = {
            "trade_classification_id": str(row["id"]),
            "market_id": str(row["market_id"]),
            "primary_trade_type": primary_trade_type,
            "assigned_bucket_class": assigned_bucket,
            "classification_confidence": confidence,
            "risk_posture_class": risk_posture,
            "bucket_target_fraction": target_fraction,
            "bucket_cap_fraction": cap_fraction,
            "base_deployment_fraction": base_deployment,
            "deployment_fraction": deployment_fraction,
            "risk_multiplier": risk_multiplier,
            "occupancy_model": "run_local_bucket_occupancy_v1",
            "bucket_occupancy_before": current_bucket_occupancy,
            "bucket_occupancy_after": occupancy_totals.get(assigned_bucket, current_bucket_occupancy),
            "suggested_bucket_class": row["suggested_bucket_class"],
            "secondary_trade_types": row["secondary_trade_types_json"],
        }
        return {
            "assigned_bucket_class": assigned_bucket,
            "bucket_target_fraction": target_fraction,
            "bucket_cap_fraction": cap_fraction,
            "deployment_fraction": deployment_fraction,
            "occupancy_status": occupancy_status,
            "deployability_class": deployability_class,
            "reason_codes": reason_codes,
            "reason_text": reason_text,
            "explanation": explanation,
        }


def _mapping_reason(primary_trade_type: str) -> str:
    mapping = {
        "FAST_TRADE": "mapped_fast_bucket",
        "RISKY_HIGHER_UPSIDE": "mapped_risky_bucket",
        "WHALE_FOLLOW": "mapped_whale_bucket",
        "SLOW_CONVICTION": "mapped_conviction_bucket",
        "NO_TRADE": "no_trade_blocked",
    }
    return mapping.get(primary_trade_type, "mapped_unknown_bucket")


def _build_reason_text(*, bucket: str, deployment_fraction: float, occupancy_status: str, deployability_class: str) -> str:
    if deployability_class == "BLOCKED":
        return f"Allocation blocked for {bucket}; deployment fraction remains {deployment_fraction:.2f}."
    if deployability_class == "SATURATED":
        return f"Bucket {bucket} is saturated; no new deployment was allowed."
    if deployability_class == "LIMITED":
        return f"Bucket {bucket} is near cap, so deployment was limited to {deployment_fraction:.2f}."
    return f"Bucket {bucket} remains {occupancy_status.lower()} and supports deployment of {deployment_fraction:.2f}."


def _clamp(value: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, round(value, 5)))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic bucket allocation for persisted trade classifications.")
    parser.add_argument("--trade-classification-ids", nargs="+", help="Explicit trade classification ids to allocate.")
    parser.add_argument("--trade-classification-run-id", help="Allocate all classifications from a persisted trade classification run.")
    parser.add_argument("--source-ref", help="Optional source reference for auditability.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = BucketAllocationService()

    if args.trade_classification_ids:
        result = service.allocate_classifications(
            args.trade_classification_ids,
            source_type="bucket_allocation_cli",
            source_ref=args.source_ref,
        )
    elif args.trade_classification_run_id:
        result = service.allocate_for_classification_run(
            args.trade_classification_run_id,
            source_ref=args.source_ref,
        )
    else:
        parser.error("either --trade-classification-ids or --trade-classification-run-id is required")

    if result is None:
        print("bucket allocation disabled")
        return 1

    print(
        f"bucket_allocation_run_id={result.bucket_allocation_run_id} "
        f"status={result.status} input_count={result.input_count} "
        f"success_count={result.success_count} failure_count={result.failure_count}"
    )
    return 0 if result.status in {"COMPLETED", "COMPLETED_WITH_ERRORS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
