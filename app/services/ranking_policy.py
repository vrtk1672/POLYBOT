from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.ranking_policy_candidate import RankingPolicyCandidateContract
from app.domain.contracts.ranking_policy_run import RankingPolicyRunCloseContract, RankingPolicyRunOpenContract
from app.repositories.ranking_policy_candidates_repository import RankingPolicyCandidatesRepository
from app.repositories.ranking_policy_runs_repository import RankingPolicyRunsRepository
from app.repositories.ranking_v2_candidates_repository import RankingV2CandidatesRepository
from app.services.recorders.ranking_policy_candidate_recorder import RankingPolicyCandidateRecorder
from app.services.recorders.ranking_policy_run_recorder import RankingPolicyRunRecorder

logger = logging.getLogger(__name__)

POLICY_VERSION = "phase7b-ranking-policy-v1"
MAX_SELECTED_WITHIN_RUN = 2
HARD_BLOCK_REASON_CODES = {
    "forced_reject_guardrail",
    "trade_classification_reject",
    "blocked_bucket_allocation",
    "cognition_do_not_use",
    "missing_bucket_allocation",
    "missing_trade_classification",
}


@dataclass(slots=True)
class RankingPolicyRunResult:
    ranking_policy_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class RankingPolicyService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        policy_version: str = POLICY_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._policy_version = policy_version
        self._runs = RankingPolicyRunsRepository()
        self._candidates = RankingPolicyCandidatesRepository()
        self._ranking = RankingV2CandidatesRepository()
        self._run_recorder = RankingPolicyRunRecorder()
        self._candidate_recorder = RankingPolicyCandidateRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def apply_policy_to_candidates(
        self,
        ranking_v2_candidate_ids: list[str],
        *,
        source_type: str = "ranking_candidate_batch",
        source_ref: str | None = None,
        ranking_v2_run_id: str | None = None,
    ) -> RankingPolicyRunResult | None:
        if not self.enabled:
            return None
        if not ranking_v2_candidate_ids:
            raise ValueError("at least one ranking_v2_candidate_id is required")

        normalized_ids = [str(candidate_id) for candidate_id in ranking_v2_candidate_ids]
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    RankingPolicyRunOpenContract(
                        id=run_id,
                        ranking_v2_run_id=_optional_str(ranking_v2_run_id),
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        policy_version=self._policy_version,
                        started_at=started_at,
                        input_count=len(normalized_ids),
                        metadata_json={
                            "policy_version": self._policy_version,
                            "source_ref": _optional_str(source_ref),
                            "max_selected_within_run": MAX_SELECTED_WITHIN_RUN,
                        },
                    ),
                )
                opened_run = True

                rows: list[dict[str, object]] = []
                for candidate_id in normalized_ids:
                    row = self._ranking.get_by_id(conn, candidate_id)
                    if row is None:
                        logger.exception("ranking_policy_missing_candidate id=%s", candidate_id)
                        failure_count += 1
                        continue
                    rows.append(dict(row))

                rows.sort(key=lambda row: (int(row["rank_position"]), -float(row["total_rank_score"])))
                selected_count = 0

                for row in rows:
                    try:
                        evaluated = self._evaluate_candidate(row, selected_count=selected_count)
                        contract = RankingPolicyCandidateContract(
                            id=str(uuid4()),
                            ranking_policy_run_id=run_id,
                            market_id=str(row["market_id"]),
                            ranking_v2_candidate_id=str(row["id"]),
                            total_rank_score=float(row["total_rank_score"]),
                            rank_position=int(row["rank_position"]),
                            rank_tier_class=str(row["rank_tier_class"]),
                            gate_decision_class=str(evaluated["gate_decision_class"]),
                            gate_priority_class=str(evaluated["gate_priority_class"]),
                            max_selected_within_run=MAX_SELECTED_WITHIN_RUN,
                            selection_reason_codes_json=list(evaluated["reason_codes"]),
                            selection_reason_text=str(evaluated["reason_text"]),
                            policy_explanation_json=dict(evaluated["explanation"]),
                            policy_version=self._policy_version,
                        )
                        self._candidate_recorder.record(conn, contract)
                        if evaluated["gate_decision_class"] == "SELECTABLE":
                            selected_count += 1
                        success_count += 1
                    except Exception:
                        logger.exception("ranking_policy_candidate_failed market_id=%s", row["market_id"])
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    RankingPolicyRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "policy_version": self._policy_version,
                            "source_ref": _optional_str(source_ref),
                            "max_selected_within_run": MAX_SELECTED_WITHIN_RUN,
                            "selected_count": selected_count,
                        },
                    ),
                )

            return RankingPolicyRunResult(
                ranking_policy_run_id=run_id,
                status=status,
                input_count=len(normalized_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("ranking_policy_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        RankingPolicyRunOpenContract(
                            id=run_id,
                            ranking_v2_run_id=_optional_str(ranking_v2_run_id),
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            policy_version=self._policy_version,
                            started_at=started_at,
                            input_count=len(normalized_ids),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    RankingPolicyRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_ids)),
                        metadata_json={"error": str(exc), "policy_version": self._policy_version},
                    ),
                )
            return RankingPolicyRunResult(
                ranking_policy_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_ids)),
            )

    def apply_policy_to_ranking_run(self, ranking_v2_run_id: str, *, source_ref: str | None = None) -> RankingPolicyRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._ranking.list_for_run(conn, ranking_v2_run_id)
        ids = [str(row["id"]) for row in rows]
        return self.apply_policy_to_candidates(
            ids,
            source_type="ranking_v2_run",
            source_ref=source_ref or ranking_v2_run_id,
            ranking_v2_run_id=ranking_v2_run_id,
        )

    def _evaluate_candidate(self, row: dict[str, object], *, selected_count: int) -> dict[str, object]:
        rank_tier = str(row["rank_tier_class"])
        total_score = float(row["total_rank_score"])
        reason_codes = [str(code) for code in row["rank_reason_codes_json"]]
        factor_scores = dict(row["factor_scores_json"])
        explanation = dict(row["explanation_json"])

        hard_block = rank_tier == "REJECT" or any(code in HARD_BLOCK_REASON_CODES for code in reason_codes)
        gate_decision = "BLOCKED"
        gate_priority = "NONE"
        policy_reasons: list[str] = []

        if hard_block:
            gate_decision = "HARD_REJECT"
            gate_priority = "NONE"
            policy_reasons.append("hard_block_inherited_from_ranking")
        elif rank_tier == "TOP":
            if selected_count < MAX_SELECTED_WITHIN_RUN:
                gate_decision = "SELECTABLE"
                gate_priority = "PRIMARY" if selected_count == 0 else "SECONDARY"
                policy_reasons.append("top_tier_selectable")
            else:
                gate_decision = "REVIEW_ONLY"
                gate_priority = "RESERVE"
                policy_reasons.append("max_selected_reached")
        elif rank_tier == "HIGH":
            if selected_count < MAX_SELECTED_WITHIN_RUN and total_score >= 60.0:
                gate_decision = "SELECTABLE"
                gate_priority = "SECONDARY"
                policy_reasons.append("high_tier_selectable")
            elif total_score >= 55.0:
                gate_decision = "REVIEW_ONLY"
                gate_priority = "RESERVE"
                policy_reasons.append("high_tier_reserve")
            else:
                gate_decision = "BLOCKED"
                gate_priority = "NONE"
                policy_reasons.append("high_tier_below_policy_score")
        elif rank_tier == "MEDIUM":
            gate_decision = "REVIEW_ONLY"
            gate_priority = "RESERVE"
            policy_reasons.append("medium_tier_review_only")
        elif rank_tier == "LOW":
            gate_decision = "BLOCKED"
            gate_priority = "NONE"
            policy_reasons.append("low_tier_blocked")
        else:
            gate_decision = "HARD_REJECT"
            gate_priority = "NONE"
            policy_reasons.append("reject_tier_hard_block")

        if selected_count >= MAX_SELECTED_WITHIN_RUN and gate_decision == "SELECTABLE":
            gate_decision = "REVIEW_ONLY"
            gate_priority = "RESERVE"
            policy_reasons.append("max_selected_reached")

        reason_text = _reason_text(
            gate_decision=gate_decision,
            gate_priority=gate_priority,
            total_score=total_score,
        )
        policy_explanation = {
            "ranking_v2_candidate_id": str(row["id"]),
            "rank_position": int(row["rank_position"]),
            "rank_tier_class": rank_tier,
            "total_rank_score": total_score,
            "max_selected_within_run": MAX_SELECTED_WITHIN_RUN,
            "selected_count_before": selected_count,
            "hard_block": hard_block,
            "inherited_reason_codes": reason_codes,
            "factor_scores": factor_scores,
            "ranking_explanation": explanation,
        }
        return {
            "gate_decision_class": gate_decision,
            "gate_priority_class": gate_priority,
            "reason_codes": policy_reasons + reason_codes,
            "reason_text": reason_text,
            "explanation": policy_explanation,
        }


def _reason_text(*, gate_decision: str, gate_priority: str, total_score: float) -> str:
    if gate_decision == "HARD_REJECT":
        return f"Candidate is hard rejected by ranking-policy guards at score {total_score:.2f}."
    if gate_decision == "BLOCKED":
        return f"Candidate remains blocked by policy despite ranking score {total_score:.2f}."
    if gate_decision == "REVIEW_ONLY":
        return f"Candidate is reserve/review-only with priority {gate_priority.lower()} at score {total_score:.2f}."
    return f"Candidate is selectable with {gate_priority.lower()} priority at score {total_score:.2f}."


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic ranking policy selection over persisted Ranking V2 candidates.")
    parser.add_argument("--ranking-v2-candidate-ids", nargs="+", help="Explicit ranking_v2 candidate ids to evaluate.")
    parser.add_argument("--ranking-v2-run-id", help="Apply policy to a full persisted ranking_v2 run.")
    parser.add_argument("--source-ref", help="Optional source reference for auditability.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = RankingPolicyService()

    if args.ranking_v2_candidate_ids:
        result = service.apply_policy_to_candidates(
            args.ranking_v2_candidate_ids,
            source_type="ranking_policy_cli",
            source_ref=args.source_ref,
        )
    elif args.ranking_v2_run_id:
        result = service.apply_policy_to_ranking_run(
            args.ranking_v2_run_id,
            source_ref=args.source_ref,
        )
    else:
        parser.error("either --ranking-v2-candidate-ids or --ranking-v2-run-id is required")

    if result is None:
        print("ranking policy disabled")
        return 1

    print(
        f"ranking_policy_run_id={result.ranking_policy_run_id} "
        f"status={result.status} input_count={result.input_count} "
        f"success_count={result.success_count} failure_count={result.failure_count}"
    )
    return 0 if result.status in {"COMPLETED", "COMPLETED_WITH_ERRORS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
