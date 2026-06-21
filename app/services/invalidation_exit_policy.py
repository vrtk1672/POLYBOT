from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.invalidation_policy_record import InvalidationPolicyRecordContract
from app.domain.contracts.invalidation_policy_run import (
    InvalidationPolicyRunCloseContract,
    InvalidationPolicyRunOpenContract,
)
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.invalidation_policy_records_repository import InvalidationPolicyRecordsRepository
from app.repositories.invalidation_policy_runs_repository import InvalidationPolicyRunsRepository
from app.repositories.invalidation_reasonings_repository import InvalidationReasoningsRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.ranking_policy_candidates_repository import RankingPolicyCandidatesRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.services.recorders.invalidation_policy_record_recorder import InvalidationPolicyRecordRecorder
from app.services.recorders.invalidation_policy_run_recorder import InvalidationPolicyRunRecorder

logger = logging.getLogger(__name__)

POLICY_VERSION = "phase8a-invalidation-exit-policy-v1"
DEPLOYABILITY_PRESSURE = {"DEPLOYABLE": 0.00, "LIMITED": 0.25, "SATURATED": 0.45, "BLOCKED": 0.70}
RANKING_POLICY_PRESSURE = {"SELECTABLE": 0.00, "REVIEW_ONLY": 0.15, "BLOCKED": 0.30, "HARD_REJECT": 0.40}


@dataclass(slots=True)
class InvalidationPolicyRunResult:
    invalidation_policy_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class InvalidationExitPolicyService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        policy_version: str = POLICY_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._policy_version = policy_version
        self._runs = InvalidationPolicyRunsRepository()
        self._records = InvalidationPolicyRecordsRepository()
        self._markets = MarketSnapshotsRepository()
        self._ranking_policy = RankingPolicyCandidatesRepository()
        self._cognition = CognitionSummariesRepository()
        self._reasoning = InvalidationReasoningsRepository()
        self._trade_classifications = TradeClassificationsRepository()
        self._bucket_allocations = BucketAllocationsRepository()
        self._run_recorder = InvalidationPolicyRunRecorder()
        self._record_recorder = InvalidationPolicyRecordRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def evaluate_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> InvalidationPolicyRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        normalized_market_ids = [str(market_id) for market_id in market_ids]
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    InvalidationPolicyRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        policy_version=self._policy_version,
                        started_at=started_at,
                        input_count=len(normalized_market_ids),
                        metadata_json={
                            "policy_version": self._policy_version,
                            "source_ref": _optional_str(source_ref),
                            "policy_model": "invalidation_exit_policy_v1",
                        },
                    ),
                )
                opened_run = True

                for market_id in normalized_market_ids:
                    try:
                        context = self._build_context(conn, market_id)
                        if context["market_snapshot"] is None:
                            raise ValueError(f"missing market snapshot for market: {market_id}")
                        evaluated = _evaluate_policy_context(context)
                        contract = InvalidationPolicyRecordContract(
                            id=str(uuid4()),
                            invalidation_policy_run_id=run_id,
                            market_id=market_id,
                            cycle_id=_optional_str(context["cycle_id"]),
                            ranking_policy_candidate_id=_optional_str(context["ranking_policy_candidate_id"]),
                            cognition_summary_id=_optional_str(context["cognition_summary_id"]),
                            invalidation_reasoning_id=_optional_str(context["invalidation_reasoning_id"]),
                            trade_classification_id=_optional_str(context["trade_classification_id"]),
                            bucket_allocation_id=_optional_str(context["bucket_allocation_id"]),
                            invalidation_state_class=str(evaluated["invalidation_state_class"]),
                            exit_policy_class=str(evaluated["exit_policy_class"]),
                            invalidation_severity_score=float(evaluated["invalidation_severity_score"]),
                            exit_urgency_score=float(evaluated["exit_urgency_score"]),
                            deployment_gate_effect=str(evaluated["deployment_gate_effect"]),
                            policy_reason_codes_json=list(evaluated["reason_codes"]),
                            policy_reason_text=str(evaluated["reason_text"]),
                            explanation_json=dict(evaluated["explanation"]),
                            policy_version=self._policy_version,
                        )
                        self._record_recorder.record(conn, contract)
                        success_count += 1
                    except Exception:
                        logger.exception("invalidation_policy_market_failed market_id=%s", market_id)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    InvalidationPolicyRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "policy_version": self._policy_version,
                            "source_ref": _optional_str(source_ref),
                            "policy_model": "invalidation_exit_policy_v1",
                        },
                    ),
                )

            return InvalidationPolicyRunResult(
                invalidation_policy_run_id=run_id,
                status=status,
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("invalidation_policy_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        InvalidationPolicyRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            policy_version=self._policy_version,
                            started_at=started_at,
                            input_count=len(normalized_market_ids),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    InvalidationPolicyRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_market_ids)),
                        metadata_json={"error": str(exc), "policy_version": self._policy_version},
                    ),
                )
            return InvalidationPolicyRunResult(
                invalidation_policy_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_market_ids)),
            )

    def evaluate_cycle(self, cycle_id: str, *, source_ref: str | None = None) -> InvalidationPolicyRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._markets.list_for_cycle(conn, cycle_id)
        market_ids = [str(row["market_id"]) for row in rows]
        return self.evaluate_markets(market_ids, source_type="cycle", source_ref=source_ref or cycle_id)

    def evaluate_ranking_policy_run(
        self,
        ranking_policy_run_id: str,
        *,
        source_ref: str | None = None,
    ) -> InvalidationPolicyRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._ranking_policy.list_for_run(conn, ranking_policy_run_id)
        market_ids = [str(row["market_id"]) for row in rows]
        return self.evaluate_markets(market_ids, source_type="ranking_policy_run", source_ref=source_ref or ranking_policy_run_id)

    def _build_context(self, conn, market_id: str) -> dict[str, object]:  # noqa: ANN001
        market = self._markets.get_latest_for_market(conn, market_id)
        cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
        reasoning_rows = self._reasoning.list_for_market(conn, market_id, 1)
        trade_classification = self._trade_classifications.get_latest_by_market(conn, market_id)
        bucket_allocation = self._bucket_allocations.get_latest_by_market(conn, market_id)
        ranking_policy = self._ranking_policy.get_latest_by_market(conn, market_id)
        cycle_id = str(market["cycle_id"]) if market is not None and market["cycle_id"] is not None else None
        cognition = dict(cognition_rows[0]) if cognition_rows else None
        reasoning = dict(reasoning_rows[0]) if reasoning_rows else None

        return {
            "market_id": market_id,
            "cycle_id": cycle_id,
            "market_snapshot": dict(market) if market is not None else None,
            "ranking_policy_candidate_id": str(ranking_policy["id"]) if ranking_policy is not None else None,
            "cognition_summary_id": str(cognition["id"]) if cognition is not None else None,
            "invalidation_reasoning_id": str(reasoning["id"]) if reasoning is not None else None,
            "trade_classification_id": str(trade_classification["id"]) if trade_classification is not None else None,
            "bucket_allocation_id": str(bucket_allocation["id"]) if bucket_allocation is not None else None,
            "ranking_policy_candidate": dict(ranking_policy) if ranking_policy is not None else None,
            "cognition_summary": cognition,
            "invalidation_reasoning": reasoning,
            "trade_classification": dict(trade_classification) if trade_classification is not None else None,
            "bucket_allocation": dict(bucket_allocation) if bucket_allocation is not None else None,
        }


def _evaluate_policy_context(context: dict[str, object]) -> dict[str, object]:
    cognition = dict(context["cognition_summary"]) if context["cognition_summary"] is not None else None
    reasoning = dict(context["invalidation_reasoning"]) if context["invalidation_reasoning"] is not None else None
    trade_classification = dict(context["trade_classification"]) if context["trade_classification"] is not None else None
    bucket_allocation = dict(context["bucket_allocation"]) if context["bucket_allocation"] is not None else None
    ranking_policy = dict(context["ranking_policy_candidate"]) if context["ranking_policy_candidate"] is not None else None

    reason_codes: list[str] = []

    sparse_context = cognition is None and reasoning is None
    caution_score = _clamp(float(cognition["caution_score"])) if cognition is not None and cognition["caution_score"] is not None else 0.55
    usability = str(cognition["usability_class"]).upper() if cognition is not None and cognition["usability_class"] is not None else "UNKNOWN"
    conclusion = str(cognition["cognition_conclusion_class"]).upper() if cognition is not None and cognition["cognition_conclusion_class"] is not None else "UNKNOWN"
    invalidation_risk = _clamp(float(reasoning["invalidation_risk_score"])) if reasoning is not None and reasoning["invalidation_risk_score"] is not None else 0.45
    degradation = _clamp(float(reasoning["confidence_degradation_score"])) if reasoning is not None and reasoning["confidence_degradation_score"] is not None else 0.45
    contradiction = _clamp(float(reasoning["contradiction_strength_score"])) if reasoning is not None and reasoning["contradiction_strength_score"] is not None else 0.40
    thesis_effect = str(reasoning["thesis_effect_class"]).upper() if reasoning is not None and reasoning["thesis_effect_class"] is not None else "UNKNOWN"
    advisory_action = str(reasoning["advisory_action_class"]).upper() if reasoning is not None and reasoning["advisory_action_class"] is not None else "NONE"
    risk_posture = str(trade_classification["risk_posture_class"]).upper() if trade_classification is not None and trade_classification["risk_posture_class"] is not None else "DO_NOT_DEPLOY"
    deployability = str(bucket_allocation["deployability_class"]).upper() if bucket_allocation is not None and bucket_allocation["deployability_class"] is not None else "BLOCKED"
    ranking_gate = str(ranking_policy["gate_decision_class"]).upper() if ranking_policy is not None and ranking_policy["gate_decision_class"] is not None else "BLOCKED"

    if sparse_context:
        reason_codes.append("sparse_policy_context")
    if usability == "DO_NOT_USE":
        reason_codes.append("cognition_do_not_use")
    if deployability == "BLOCKED":
        reason_codes.append("bucket_deployability_blocked")
    elif deployability == "SATURATED":
        reason_codes.append("bucket_deployability_saturated")
    if ranking_gate == "HARD_REJECT":
        reason_codes.append("ranking_policy_hard_reject")
    elif ranking_gate == "BLOCKED":
        reason_codes.append("ranking_policy_blocked")

    if thesis_effect in {"INVALIDATES_THESIS", "BREAKS_THESIS"}:
        reason_codes.append("explicit_thesis_break")
        invalidation_risk = max(invalidation_risk, 0.90)
        degradation = max(degradation, 0.85)
        contradiction = max(contradiction, 0.85)
    elif thesis_effect in {"WARNING", "WEAKENS_THESIS", "CONTRADICTS_THESIS"}:
        reason_codes.append("warning_level_invalidation_pressure")
    elif thesis_effect in {"SUPPORTS_THESIS", "NEUTRAL"}:
        reason_codes.append("supportive_or_neutral_invalidation_context")

    severity = _clamp((invalidation_risk * 0.40) + (degradation * 0.30) + (contradiction * 0.30))
    if sparse_context:
        severity = 0.30
    if usability == "DO_NOT_USE":
        severity = max(severity, 0.82)
    if advisory_action in {"DEGRADE_CONFIDENCE", "PREPARE_INVALIDATION_REVIEW", "REQUIRE_CONFIRMATION"}:
        reason_codes.append("invalidation_action_degrade")

    deployability_pressure = DEPLOYABILITY_PRESSURE.get(deployability, 0.60)
    ranking_pressure = RANKING_POLICY_PRESSURE.get(ranking_gate, 0.25)
    urgency = _clamp((severity * 0.50) + (caution_score * 0.20) + (deployability_pressure * 0.20) + (ranking_pressure * 0.10))

    invalidation_state = "THESIS_INTACT"
    if (not sparse_context and usability == "DO_NOT_USE") or severity >= 0.78:
        invalidation_state = "INVALIDATED"
        reason_codes.append("thesis_invalidated")
    elif severity >= 0.62:
        invalidation_state = "INVALIDATION_CANDIDATE"
        reason_codes.append("thesis_invalidation_candidate")
    elif severity >= 0.42:
        invalidation_state = "DEGRADED"
        reason_codes.append("thesis_degraded")
    elif severity >= 0.22:
        invalidation_state = "WATCH"
        reason_codes.append("watch_thesis")
    else:
        reason_codes.append("thesis_intact")

    exit_policy = "HOLD"
    if invalidation_state == "INVALIDATED" or urgency >= 0.82:
        exit_policy = "EXIT_RECOMMENDED"
        reason_codes.append("exit_recommended")
    elif invalidation_state == "INVALIDATION_CANDIDATE" or urgency >= 0.65:
        exit_policy = "PREPARE_EXIT"
        reason_codes.append("prepare_exit")
    elif invalidation_state == "DEGRADED":
        exit_policy = "REDUCE_EXPOSURE"
        reason_codes.append("reduce_exposure")
    elif ranking_gate in {"BLOCKED", "HARD_REJECT"} or deployability == "BLOCKED":
        exit_policy = "BLOCK_NEW_DEPLOYMENT"
        reason_codes.append("block_new_deployment")
    elif invalidation_state == "WATCH":
        exit_policy = "MONITOR_CLOSELY"
        reason_codes.append("monitor_closely")

    deployment_gate_effect = "NONE"
    if (
        invalidation_state == "INVALIDATED"
        or exit_policy == "EXIT_RECOMMENDED"
        or ranking_gate == "HARD_REJECT"
        or deployability == "BLOCKED"
    ):
        deployment_gate_effect = "HARD_BLOCK"
        reason_codes.append("hard_block_deployment")
    elif invalidation_state in {"DEGRADED", "INVALIDATION_CANDIDATE"} or exit_policy in {
        "REDUCE_EXPOSURE",
        "PREPARE_EXIT",
        "BLOCK_NEW_DEPLOYMENT",
    }:
        deployment_gate_effect = "SOFT_BLOCK"
        reason_codes.append("soft_block_deployment")

    explanation = {
        "inputs": {
            "cognition_summary_id": _optional_str(context["cognition_summary_id"]),
            "invalidation_reasoning_id": _optional_str(context["invalidation_reasoning_id"]),
            "trade_classification_id": _optional_str(context["trade_classification_id"]),
            "bucket_allocation_id": _optional_str(context["bucket_allocation_id"]),
            "ranking_policy_candidate_id": _optional_str(context["ranking_policy_candidate_id"]),
        },
        "scores": {
            "invalidation_risk": invalidation_risk,
            "confidence_degradation": degradation,
            "contradiction_strength": contradiction,
            "caution_score": caution_score,
            "deployability_pressure": deployability_pressure,
            "ranking_policy_pressure": ranking_pressure,
            "invalidation_severity_score": severity,
            "exit_urgency_score": urgency,
        },
        "state_inputs": {
            "thesis_effect_class": thesis_effect,
            "advisory_action_class": advisory_action,
            "cognition_conclusion_class": conclusion,
            "usability_class": usability,
            "risk_posture_class": risk_posture,
            "deployability_class": deployability,
            "ranking_gate_decision_class": ranking_gate,
        },
        "policy_outputs": {
            "invalidation_state_class": invalidation_state,
            "exit_policy_class": exit_policy,
            "deployment_gate_effect": deployment_gate_effect,
        },
    }

    return {
        "invalidation_state_class": invalidation_state,
        "exit_policy_class": exit_policy,
        "invalidation_severity_score": round(severity, 4),
        "exit_urgency_score": round(urgency, 4),
        "deployment_gate_effect": deployment_gate_effect,
        "reason_codes": sorted(set(reason_codes)),
        "reason_text": _reason_text(invalidation_state, exit_policy, deployment_gate_effect),
        "explanation": explanation,
    }


def _reason_text(invalidation_state: str, exit_policy: str, deployment_gate_effect: str) -> str:
    return (
        f"Policy set {invalidation_state} with {exit_policy} and "
        f"{deployment_gate_effect} deployment gating based on persisted invalidation, cognition, ranking, and allocation context."
    )


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8A invalidation and exit policy.")
    parser.add_argument("--market-ids", nargs="*", help="Explicit market ids to evaluate.")
    parser.add_argument("--cycle-id", help="Evaluate all persisted markets from a cycle.")
    parser.add_argument("--ranking-policy-run-id", help="Evaluate markets from a ranking policy run.")
    args = parser.parse_args(argv)

    service = InvalidationExitPolicyService()
    if not service.enabled:
        print("invalidation_exit_policy_disabled")
        return 0

    result: InvalidationPolicyRunResult | None
    if args.market_ids:
        result = service.evaluate_markets(args.market_ids, source_type="cli_market_batch", source_ref="cli_market_batch")
    elif args.cycle_id:
        result = service.evaluate_cycle(args.cycle_id, source_ref=args.cycle_id)
    elif args.ranking_policy_run_id:
        result = service.evaluate_ranking_policy_run(args.ranking_policy_run_id, source_ref=args.ranking_policy_run_id)
    else:
        parser.error("one of --market-ids, --cycle-id, or --ranking-policy-run-id is required")

    if result is None:
        return 0
    print(
        "invalidation_policy_run_id={run_id} status={status} input_count={input_count} "
        "success_count={success_count} failure_count={failure_count}".format(
            run_id=result.invalidation_policy_run_id,
            status=result.status,
            input_count=result.input_count,
            success_count=result.success_count,
            failure_count=result.failure_count,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
