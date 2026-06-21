from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.ranking_v2_candidate import RankingV2CandidateContract
from app.domain.contracts.ranking_v2_run import RankingV2RunCloseContract, RankingV2RunOpenContract
from app.repositories.bucket_allocations_repository import BucketAllocationsRepository
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.ranking_v2_candidates_repository import RankingV2CandidatesRepository
from app.repositories.ranking_v2_runs_repository import RankingV2RunsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository
from app.services.recorders.ranking_v2_candidate_recorder import RankingV2CandidateRecorder
from app.services.recorders.ranking_v2_run_recorder import RankingV2RunRecorder

logger = logging.getLogger(__name__)

RANKING_VERSION = "phase7a-ranking-v2-foundation-v1"

USABILITY_MULTIPLIERS = {
    "USABLE_NOW": 1.00,
    "NEEDS_CONFIRMATION": 0.65,
    "MONITOR_ONLY": 0.40,
    "DO_NOT_USE": 0.00,
}

TRADE_TYPE_STRENGTH = {
    "FAST_TRADE": 0.80,
    "RISKY_HIGHER_UPSIDE": 0.55,
    "WHALE_FOLLOW": 0.88,
    "SLOW_CONVICTION": 0.92,
    "NO_TRADE": 0.00,
}

DEPLOYABILITY_STRENGTH = {
    "DEPLOYABLE": 1.00,
    "LIMITED": 0.65,
    "SATURATED": 0.10,
    "BLOCKED": 0.00,
}

RISK_POSTURE_PENALTY = {
    "LOW_RISK": 0.05,
    "BALANCED": 0.15,
    "ELEVATED_RISK": 0.35,
    "HIGH_RISK": 0.55,
    "DO_NOT_DEPLOY": 0.95,
}


@dataclass(slots=True)
class RankingV2RunResult:
    ranking_v2_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class RankingV2Service:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        ranking_version: str = RANKING_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._ranking_version = ranking_version
        self._runs = RankingV2RunsRepository()
        self._candidates = RankingV2CandidatesRepository()
        self._markets = MarketSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()
        self._cognition = CognitionSummariesRepository()
        self._whale_scores = WhaleMarketScoresRepository()
        self._trade_classifications = TradeClassificationsRepository()
        self._bucket_allocations = BucketAllocationsRepository()
        self._run_recorder = RankingV2RunRecorder()
        self._candidate_recorder = RankingV2CandidateRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def rank_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> RankingV2RunResult | None:
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
                    RankingV2RunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_optional_str(source_ref),
                        status="OPEN",
                        ranking_version=self._ranking_version,
                        started_at=started_at,
                        input_count=len(normalized_market_ids),
                        metadata_json={
                            "ranking_version": self._ranking_version,
                            "source_ref": _optional_str(source_ref),
                            "factor_model": "weighted_market_cognition_whale_trade_bucket_v1",
                        },
                    ),
                )
                opened_run = True

                evaluated: list[dict[str, object]] = []
                for market_id in normalized_market_ids:
                    try:
                        context = self._build_context(conn, market_id)
                        if context["market_snapshot"] is None:
                            raise ValueError(f"missing market snapshot for market: {market_id}")
                        evaluated.append(self._evaluate_market(context))
                    except Exception:
                        logger.exception("ranking_v2_context_failed market_id=%s", market_id)
                        failure_count += 1

                evaluated.sort(key=lambda row: (-float(row["total_rank_score"]), str(row["market_id"])))

                for position, row in enumerate(evaluated, start=1):
                    try:
                        tier = _rank_tier(float(row["total_rank_score"]), bool(row["forced_reject"]))
                        candidate = RankingV2CandidateContract(
                            id=str(uuid4()),
                            ranking_v2_run_id=run_id,
                            market_id=str(row["market_id"]),
                            cycle_id=_optional_str(row["cycle_id"]),
                            market_snapshot_id=int(row["market_snapshot_id"]) if row["market_snapshot_id"] is not None else None,
                            decision_id=_optional_str(row["decision_id"]),
                            cognition_summary_id=_optional_str(row["cognition_summary_id"]),
                            whale_market_score_id=_optional_str(row["whale_market_score_id"]),
                            trade_classification_id=_optional_str(row["trade_classification_id"]),
                            bucket_allocation_id=_optional_str(row["bucket_allocation_id"]),
                            total_rank_score=float(row["total_rank_score"]),
                            factor_scores_json=dict(row["factor_scores"]),
                            rank_position=position,
                            rank_tier_class=tier,
                            rank_reason_codes_json=list(row["reason_codes"]),
                            rank_reason_text=str(row["reason_text"]),
                            explanation_json=dict(row["explanation"]),
                            ranking_version=self._ranking_version,
                        )
                        self._candidate_recorder.record(conn, candidate)
                        success_count += 1
                    except Exception:
                        logger.exception("ranking_v2_candidate_failed market_id=%s", row["market_id"])
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    RankingV2RunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "ranking_version": self._ranking_version,
                            "source_ref": _optional_str(source_ref),
                            "factor_model": "weighted_market_cognition_whale_trade_bucket_v1",
                        },
                    ),
                )

            return RankingV2RunResult(
                ranking_v2_run_id=run_id,
                status=status,
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("ranking_v2_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        RankingV2RunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_optional_str(source_ref),
                            status="OPEN",
                            ranking_version=self._ranking_version,
                            started_at=started_at,
                            input_count=len(normalized_market_ids),
                            metadata_json={"source_ref": _optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    RankingV2RunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_market_ids)),
                        metadata_json={"error": str(exc), "ranking_version": self._ranking_version},
                    ),
                )
            return RankingV2RunResult(
                ranking_v2_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_market_ids)),
            )

    def rank_cycle(self, cycle_id: str, *, source_ref: str | None = None) -> RankingV2RunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            snapshots = self._markets.list_for_cycle(conn, cycle_id)
        market_ids = [str(row["market_id"]) for row in snapshots]
        return self.rank_markets(market_ids, source_type="cycle", source_ref=source_ref or cycle_id)

    def rank_latest_catalog(self, *, limit: int = 25, source_ref: str | None = None) -> RankingV2RunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._markets.list_latest_catalog(conn)
        market_ids = [str(row["market_id"]) for row in rows[: max(1, int(limit))]]
        return self.rank_markets(market_ids, source_type="latest_catalog", source_ref=source_ref or f"limit:{int(limit)}")

    def _build_context(self, conn, market_id: str) -> dict[str, object]:  # noqa: ANN001
        market = self._markets.get_latest_for_market(conn, market_id)
        cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
        whale_score = self._whale_scores.get_latest_by_market(conn, market_id)
        trade_classification = self._trade_classifications.get_latest_by_market(conn, market_id)
        bucket_allocation = self._bucket_allocations.get_latest_by_market(conn, market_id)
        decision = None
        cycle_id = None
        if market is not None and market["cycle_id"] is not None:
            cycle_id = str(market["cycle_id"])
            decision = self._decisions.get_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
        return {
            "market_id": market_id,
            "cycle_id": cycle_id,
            "market_snapshot": dict(market) if market is not None else None,
            "decision": dict(decision) if decision is not None else None,
            "cognition_summary": dict(cognition_rows[0]) if cognition_rows else None,
            "whale_market_score": dict(whale_score) if whale_score is not None else None,
            "trade_classification": dict(trade_classification) if trade_classification is not None else None,
            "bucket_allocation": dict(bucket_allocation) if bucket_allocation is not None else None,
        }

    def _evaluate_market(self, context: dict[str, object]) -> dict[str, object]:
        market = context["market_snapshot"]
        cognition = context["cognition_summary"]
        whale = context["whale_market_score"]
        trade_classification = context["trade_classification"]
        bucket_allocation = context["bucket_allocation"]
        decision = context["decision"]

        market_quality_factor = _market_quality_factor(market)
        cognition_factor = _cognition_factor(cognition)
        whale_factor = _whale_factor(whale)
        trade_type_factor = _trade_type_factor(trade_classification)
        capital_deployability_factor = _capital_deployability_factor(bucket_allocation)
        time_pressure_factor = _time_pressure_factor(market)
        risk_penalty = _risk_penalty(cognition, whale, trade_classification)

        weighted_positive = (
            0.20 * market_quality_factor
            + 0.24 * cognition_factor
            + 0.18 * whale_factor
            + 0.16 * trade_type_factor
            + 0.12 * capital_deployability_factor
            + 0.10 * time_pressure_factor
        )
        total_rank_score = round(max(0.0, min(100.0, (weighted_positive - (0.20 * risk_penalty)) * 100.0)), 4)

        factor_scores = {
            "market_quality_factor": round(market_quality_factor, 5),
            "cognition_factor": round(cognition_factor, 5),
            "whale_factor": round(whale_factor, 5),
            "trade_type_factor": round(trade_type_factor, 5),
            "capital_deployability_factor": round(capital_deployability_factor, 5),
            "time_pressure_factor": round(time_pressure_factor, 5),
            "risk_penalty": round(risk_penalty, 5),
        }

        reason_codes: list[str] = []
        if trade_classification is None:
            reason_codes.append("missing_trade_classification")
        elif str(trade_classification["primary_trade_type"]) == "NO_TRADE":
            reason_codes.append("trade_classification_reject")
        elif float(trade_classification["classification_confidence"]) >= 0.75:
            reason_codes.append("strong_trade_classification")

        if cognition is None:
            reason_codes.append("missing_cognition_context")
        else:
            usability = str(cognition["usability_class"])
            if usability == "USABLE_NOW":
                reason_codes.append("usable_cognition_support")
            elif usability == "DO_NOT_USE":
                reason_codes.append("cognition_do_not_use")

        if whale is not None:
            if float(whale["smart_whale_alignment_score"]) >= 0.60:
                reason_codes.append("aligned_whale_support")
            if float(whale["whale_reversal_risk"]) >= 0.55:
                reason_codes.append("elevated_whale_reversal_risk")

        if bucket_allocation is None:
            reason_codes.append("missing_bucket_allocation")
        else:
            deployability = str(bucket_allocation["deployability_class"])
            if deployability == "DEPLOYABLE":
                reason_codes.append("deployable_bucket_support")
            elif deployability == "BLOCKED":
                reason_codes.append("blocked_bucket_allocation")

        forced_reject = (
            trade_classification is None
            or bucket_allocation is None
            or cognition is None
            or str(trade_classification["primary_trade_type"]) == "NO_TRADE"
            or str(bucket_allocation["deployability_class"]) == "BLOCKED"
            or str(cognition["usability_class"]) == "DO_NOT_USE"
        )
        if forced_reject:
            total_rank_score = min(total_rank_score, 19.99)
            reason_codes.append("forced_reject_guardrail")

        if market is not None and float(market["liquidity"] or 0.0) >= 40000.0:
            reason_codes.append("strong_liquidity_context")
        if decision is not None and bool(decision["selected"]):
            reason_codes.append("selected_decision_context")

        reason_text = _reason_text(total_rank_score, forced_reject)
        explanation = {
            "market_snapshot_id": int(market["id"]) if market is not None and market["id"] is not None else None,
            "cycle_id": context["cycle_id"],
            "decision_id": _optional_str(decision["id"]) if decision is not None else None,
            "cognition_summary_id": _optional_str(cognition["id"]) if cognition is not None else None,
            "whale_market_score_id": _optional_str(whale["id"]) if whale is not None else None,
            "trade_classification_id": _optional_str(trade_classification["id"]) if trade_classification is not None else None,
            "bucket_allocation_id": _optional_str(bucket_allocation["id"]) if bucket_allocation is not None else None,
            "factor_scores": factor_scores,
            "weighted_positive_score": round(weighted_positive, 5),
            "forced_reject": forced_reject,
            "decision_selected": bool(decision["selected"]) if decision is not None else False,
        }
        return {
            "market_id": context["market_id"],
            "cycle_id": context["cycle_id"],
            "market_snapshot_id": market["id"] if market is not None else None,
            "decision_id": decision["id"] if decision is not None else None,
            "cognition_summary_id": cognition["id"] if cognition is not None else None,
            "whale_market_score_id": whale["id"] if whale is not None else None,
            "trade_classification_id": trade_classification["id"] if trade_classification is not None else None,
            "bucket_allocation_id": bucket_allocation["id"] if bucket_allocation is not None else None,
            "total_rank_score": total_rank_score,
            "factor_scores": factor_scores,
            "reason_codes": reason_codes,
            "reason_text": reason_text,
            "explanation": explanation,
            "forced_reject": forced_reject,
        }


def _market_quality_factor(market: dict[str, object] | None) -> float:
    if market is None:
        return 0.0
    liquidity = min(float(market["liquidity"] or 0.0) / 50000.0, 1.0)
    spread = float(market["spread"] or 0.0)
    spread_score = max(0.0, min(1.0, 1.0 - (spread / 0.08)))
    tradable = 1.0 if bool(market["accepting_orders"]) else 0.0
    orderbook = 1.0 if bool(market["orderbook_enabled"]) else 0.0
    competitive = max(0.0, min(1.0, float(market["competitive"] or 0.0)))
    return _clamp((0.40 * liquidity) + (0.25 * spread_score) + (0.20 * tradable) + (0.05 * orderbook) + (0.10 * competitive))


def _cognition_factor(cognition: dict[str, object] | None) -> float:
    if cognition is None:
        return 0.0
    confidence = _clamp(float(cognition["overall_confidence_score"] or 0.0))
    caution = _clamp(float(cognition["caution_score"] or 0.0))
    usability = USABILITY_MULTIPLIERS.get(str(cognition["usability_class"]), 0.0)
    return _clamp(confidence * usability * (1.0 - (0.60 * caution)))


def _whale_factor(whale: dict[str, object] | None) -> float:
    if whale is None:
        return 0.0
    presence = _clamp(float(whale["whale_presence_score"] or 0.0))
    conviction = _clamp(float(whale["whale_conviction_score"] or 0.0))
    alignment = _clamp(float(whale["smart_whale_alignment_score"] or 0.0))
    reversal = _clamp(float(whale["whale_reversal_risk"] or 0.0))
    return _clamp((0.35 * presence) + (0.30 * conviction) + (0.25 * alignment) + (0.10 * (1.0 - reversal)))


def _trade_type_factor(trade_classification: dict[str, object] | None) -> float:
    if trade_classification is None:
        return 0.0
    trade_type = str(trade_classification["primary_trade_type"])
    confidence = _clamp(float(trade_classification["classification_confidence"] or 0.0))
    strength = TRADE_TYPE_STRENGTH.get(trade_type, 0.0)
    return _clamp(strength * confidence)


def _capital_deployability_factor(bucket_allocation: dict[str, object] | None) -> float:
    if bucket_allocation is None:
        return 0.0
    deployability = DEPLOYABILITY_STRENGTH.get(str(bucket_allocation["deployability_class"]), 0.0)
    target = float(bucket_allocation["bucket_target_fraction"] or 0.0)
    deployment = float(bucket_allocation["deployment_fraction"] or 0.0)
    occupancy = str(bucket_allocation["occupancy_status"])
    deployment_strength = 0.0 if target <= 0 else min(deployment / target, 1.0)
    occupancy_adjustment = 0.0 if occupancy == "BLOCKED" else (0.10 if occupancy in {"EMPTY", "AVAILABLE"} else -0.05)
    return _clamp((0.60 * deployability) + (0.40 * deployment_strength) + occupancy_adjustment)


def _time_pressure_factor(market: dict[str, object] | None) -> float:
    if market is None:
        return 0.0
    seconds = int(market["time_to_close_seconds"] or 0)
    hours = max(0.0, seconds / 3600.0)
    if hours <= 0:
        return 0.0
    if hours <= 6:
        return 0.40
    if hours <= 48:
        return 1.00
    if hours <= 168:
        return 0.80
    if hours <= 336:
        return 0.60
    return 0.45


def _risk_penalty(
    cognition: dict[str, object] | None,
    whale: dict[str, object] | None,
    trade_classification: dict[str, object] | None,
) -> float:
    caution = 0.70 if cognition is None else _clamp(float(cognition["caution_score"] or 0.0))
    reversal = 0.40 if whale is None else _clamp(float(whale["whale_reversal_risk"] or 0.0))
    posture_penalty = 0.55
    if trade_classification is not None:
        posture_penalty = RISK_POSTURE_PENALTY.get(str(trade_classification["risk_posture_class"]), 0.55)
    return _clamp((0.50 * posture_penalty) + (0.30 * caution) + (0.20 * reversal))


def _rank_tier(total_rank_score: float, forced_reject: bool) -> str:
    if forced_reject or total_rank_score < 25.0:
        return "REJECT"
    if total_rank_score >= 75.0:
        return "TOP"
    if total_rank_score >= 60.0:
        return "HIGH"
    if total_rank_score >= 45.0:
        return "MEDIUM"
    return "LOW"


def _reason_text(total_rank_score: float, forced_reject: bool) -> str:
    if forced_reject:
        return f"Ranking candidate was rejected by upstream guardrails; total score held at {total_rank_score:.2f}."
    if total_rank_score >= 75.0:
        return f"Ranking candidate shows top-tier aggregate strength with score {total_rank_score:.2f}."
    if total_rank_score >= 60.0:
        return f"Ranking candidate remains high quality with score {total_rank_score:.2f}."
    if total_rank_score >= 45.0:
        return f"Ranking candidate is usable but mixed, with score {total_rank_score:.2f}."
    return f"Ranking candidate is weak and should stay low priority at score {total_rank_score:.2f}."


def _clamp(value: float, *, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, round(value, 5)))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic Ranking Engine V2 over persisted market contexts.")
    parser.add_argument("--market-ids", nargs="+", help="Explicit market ids to rank.")
    parser.add_argument("--cycle-id", help="Rank all persisted market snapshots for a cycle.")
    parser.add_argument("--latest-catalog", action="store_true", help="Rank latest persisted catalog markets.")
    parser.add_argument("--limit", type=int, default=25, help="Catalog limit when using --latest-catalog.")
    parser.add_argument("--source-ref", help="Optional source reference for auditability.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    service = RankingV2Service()

    if args.market_ids:
        result = service.rank_markets(args.market_ids, source_type="ranking_v2_cli", source_ref=args.source_ref)
    elif args.cycle_id:
        result = service.rank_cycle(args.cycle_id, source_ref=args.source_ref)
    elif args.latest_catalog:
        result = service.rank_latest_catalog(limit=args.limit, source_ref=args.source_ref)
    else:
        parser.error("one of --market-ids, --cycle-id, or --latest-catalog is required")

    if result is None:
        print("ranking v2 disabled")
        return 1

    print(
        f"ranking_v2_run_id={result.ranking_v2_run_id} "
        f"status={result.status} input_count={result.input_count} "
        f"success_count={result.success_count} failure_count={result.failure_count}"
    )
    return 0 if result.status in {"COMPLETED", "COMPLETED_WITH_ERRORS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
