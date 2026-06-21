from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.trade_classification import TradeClassificationContract
from app.domain.contracts.trade_classification_run import (
    TradeClassificationRunCloseContract,
    TradeClassificationRunOpenContract,
)
from app.repositories.cognition_summaries_repository import CognitionSummariesRepository
from app.repositories.cycle_repository import CycleRepository
from app.repositories.decision_ledger_repository import DecisionLedgerRepository
from app.repositories.market_snapshots_repository import MarketSnapshotsRepository
from app.repositories.trade_classification_runs_repository import TradeClassificationRunsRepository
from app.repositories.trade_classifications_repository import TradeClassificationsRepository
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository
from app.services.recorders.trade_classification_recorder import TradeClassificationRecorder
from app.services.recorders.trade_classification_run_recorder import TradeClassificationRunRecorder

logger = logging.getLogger(__name__)

CLASSIFIER_VERSION = "phase6a-trade-classification-v1"
PRIMARY_TYPES = {"FAST_TRADE", "RISKY_HIGHER_UPSIDE", "WHALE_FOLLOW", "SLOW_CONVICTION", "NO_TRADE"}
RISK_POSTURES = {"LOW_RISK", "BALANCED", "ELEVATED_RISK", "HIGH_RISK", "DO_NOT_DEPLOY"}
BUCKET_CLASSES = {"FAST_BUCKET", "RISKY_BUCKET", "WHALE_BUCKET", "CONVICTION_BUCKET", "NO_BUCKET"}


@dataclass(slots=True)
class TradeClassificationRunResult:
    trade_classification_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class TradeClassificationService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        classifier_version: str = CLASSIFIER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._classifier_version = classifier_version
        self._runs = TradeClassificationRunsRepository()
        self._classifications = TradeClassificationsRepository()
        self._markets = MarketSnapshotsRepository()
        self._decisions = DecisionLedgerRepository()
        self._cognition = CognitionSummariesRepository()
        self._whale_scores = WhaleMarketScoresRepository()
        self._cycles = CycleRepository()
        self._run_recorder = TradeClassificationRunRecorder()
        self._classification_recorder = TradeClassificationRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def classify_markets(
        self,
        market_ids: list[str],
        *,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> TradeClassificationRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        normalized_market_ids = [_normalize_market_id(market_id) for market_id in market_ids]
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    TradeClassificationRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_as_optional_str(source_ref),
                        status="OPEN",
                        classifier_version=self._classifier_version,
                        started_at=started_at,
                        input_count=len(normalized_market_ids),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "classifier_version": self._classifier_version,
                        },
                    ),
                )
                opened_run = True

                for market_id in normalized_market_ids:
                    try:
                        context = self._build_context(conn, market_id)
                        result = _classify_market_context(context)
                        contract = TradeClassificationContract(
                            id=str(uuid4()),
                            trade_classification_run_id=run_id,
                            market_id=market_id,
                            cycle_id=context["cycle_id"],
                            decision_id=context["decision_id"],
                            cognition_summary_id=context["cognition_summary_id"],
                            whale_market_score_id=context["whale_market_score_id"],
                            primary_trade_type=result["primary_trade_type"],
                            secondary_trade_types_json=result["secondary_trade_types"],
                            classification_confidence=result["classification_confidence"],
                            risk_posture_class=result["risk_posture_class"],
                            suggested_bucket_class=result["suggested_bucket_class"],
                            classification_reason_codes_json=result["reason_codes"],
                            classification_reason_text=result["reason_text"],
                            explanation_json=result["explanation"],
                            classifier_version=self._classifier_version,
                        )
                        self._classification_recorder.record(conn, contract)
                        success_count += 1
                    except Exception:
                        logger.exception("trade_classification_market_failed market_id=%s", market_id)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    TradeClassificationRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "classifier_version": self._classifier_version,
                            "source_ref": _as_optional_str(source_ref),
                        },
                    ),
                )

            return TradeClassificationRunResult(
                trade_classification_run_id=run_id,
                status=status,
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("trade_classification_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        TradeClassificationRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_as_optional_str(source_ref),
                            status="OPEN",
                            classifier_version=self._classifier_version,
                            started_at=started_at,
                            input_count=len(normalized_market_ids),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    TradeClassificationRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_market_ids)),
                        metadata_json={"error": str(exc), "classifier_version": self._classifier_version},
                    ),
                )
            return TradeClassificationRunResult(
                trade_classification_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_market_ids)),
            )

    def classify_cycle(
        self,
        cycle_id: str,
        *,
        source_ref: str | None = None,
    ) -> TradeClassificationRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            cycle = self._cycles.get_cycle(conn, cycle_id)
            if cycle is None:
                raise ValueError(f"cycle not found: {cycle_id}")
            snapshots = self._markets.list_for_cycle(conn, cycle_id)
        market_ids = [str(row["market_id"]) for row in snapshots]
        return self.classify_markets(
            market_ids,
            source_type="cycle_market_batch",
            source_ref=source_ref or cycle_id,
        )

    def _build_context(self, conn, market_id: str) -> dict[str, object]:
        market = self._markets.get_latest_for_market(conn, market_id)
        if market is None:
            raise ValueError(f"market snapshot not found: {market_id}")

        cycle_id = str(market["cycle_id"]) if market["cycle_id"] is not None else None
        decision = None
        if cycle_id is not None:
            decision = self._decisions.get_for_cycle_market(conn, cycle_id=cycle_id, market_id=market_id)
        cognition_rows = self._cognition.list_for_market(conn, market_id, 1)
        cognition = dict(cognition_rows[0]) if cognition_rows else None
        whale_score_row = self._whale_scores.get_latest_by_market(conn, market_id)
        whale_score = dict(whale_score_row) if whale_score_row is not None else None

        return {
            "market_id": market_id,
            "cycle_id": cycle_id,
            "decision_id": str(decision["id"]) if decision is not None else None,
            "cognition_summary_id": str(cognition["id"]) if cognition is not None else None,
            "whale_market_score_id": str(whale_score["id"]) if whale_score is not None else None,
            "market_snapshot": dict(market),
            "decision": dict(decision) if decision is not None else None,
            "cognition_summary": cognition,
            "whale_market_score": whale_score,
        }


def _classify_market_context(context: dict[str, object]) -> dict[str, object]:
    market = dict(context["market_snapshot"])
    decision = dict(context["decision"]) if context["decision"] is not None else None
    cognition = dict(context["cognition_summary"]) if context["cognition_summary"] is not None else None
    whale = dict(context["whale_market_score"]) if context["whale_market_score"] is not None else None

    time_to_close_seconds = market.get("time_to_close_seconds")
    time_to_close_hours = (
        float(time_to_close_seconds) / 3600.0
        if time_to_close_seconds is not None
        else None
    )
    liquidity = float(market.get("liquidity") or 0.0)
    decision_selected = bool(decision["selected"]) if decision is not None else False
    decision_confidence = float(decision["confidence"] or 0.0) if decision is not None else 0.0
    decision_type = str(decision["decision_type"]) if decision is not None else None
    expected_edge = float(decision["expected_edge_proxy"] or 0.0) if decision is not None else 0.0

    cognition_confidence = float(cognition["overall_confidence_score"]) if cognition is not None and cognition["overall_confidence_score"] is not None else 0.0
    caution_score = float(cognition["caution_score"]) if cognition is not None and cognition["caution_score"] is not None else 1.0
    usability = str(cognition["usability_class"]) if cognition is not None and cognition["usability_class"] is not None else "DO_NOT_USE"
    cognition_conclusion = (
        str(cognition["cognition_conclusion_class"])
        if cognition is not None and cognition["cognition_conclusion_class"] is not None
        else None
    )

    whale_presence = float(whale["whale_presence_score"]) if whale is not None else 0.0
    whale_conviction = float(whale["whale_conviction_score"]) if whale is not None else 0.0
    whale_alignment = float(whale["smart_whale_alignment_score"]) if whale is not None else 0.0
    whale_reversal_risk = float(whale["whale_reversal_risk"]) if whale is not None else 0.0

    if decision_type == "BLOCK" or usability in {"DO_NOT_USE", "TOO_AMBIGUOUS"} or cognition_conclusion in {"CONTRADICTORY", "INVALIDATION_CANDIDATE"}:
        primary_trade_type = "NO_TRADE"
        reason_codes = ["unusable_or_blocked_context"]
    elif whale_reversal_risk >= 0.75:
        primary_trade_type = "NO_TRADE"
        reason_codes = ["whale_reversal_risk_too_high"]
    elif whale_presence >= 0.55 and whale_conviction >= 0.55 and whale_reversal_risk < 0.50 and usability != "DO_NOT_USE":
        primary_trade_type = "WHALE_FOLLOW"
        reason_codes = ["strong_whale_follow_signal"]
    elif time_to_close_hours is not None and time_to_close_hours <= 48 and cognition_confidence >= 0.60 and caution_score <= 0.60:
        primary_trade_type = "FAST_TRADE"
        reason_codes = ["compressed_time_window"]
    elif cognition_confidence >= 0.70 and caution_score <= 0.45 and (time_to_close_hours is None or time_to_close_hours > 48):
        primary_trade_type = "SLOW_CONVICTION"
        reason_codes = ["high_cognition_conviction"]
    elif (decision_selected or cognition_confidence >= 0.55 or whale_presence >= 0.45) and caution_score < 0.80 and usability != "DO_NOT_USE":
        primary_trade_type = "RISKY_HIGHER_UPSIDE"
        reason_codes = ["selected_with_elevated_risk"]
    else:
        primary_trade_type = "NO_TRADE"
        reason_codes = ["sparse_or_weak_context"]

    secondary_trade_types: list[str] = []
    if primary_trade_type != "WHALE_FOLLOW" and whale_presence >= 0.55 and whale_alignment >= 0.55:
        secondary_trade_types.append("WHALE_FOLLOW")
    if primary_trade_type != "FAST_TRADE" and time_to_close_hours is not None and time_to_close_hours <= 48 and cognition_confidence >= 0.55:
        secondary_trade_types.append("FAST_TRADE")
    if primary_trade_type != "SLOW_CONVICTION" and cognition_confidence >= 0.68 and caution_score <= 0.50:
        secondary_trade_types.append("SLOW_CONVICTION")
    if primary_trade_type != "RISKY_HIGHER_UPSIDE" and decision_selected and caution_score >= 0.50 and usability != "DO_NOT_USE":
        secondary_trade_types.append("RISKY_HIGHER_UPSIDE")
    secondary_trade_types = list(dict.fromkeys(secondary_trade_types))

    classification_confidence = _clamp_score(
        0.25 * decision_confidence
        + 0.35 * cognition_confidence
        + 0.20 * whale_alignment
        + 0.10 * min(1.0, liquidity / 50000.0)
        + 0.10 * (1.0 - min(1.0, caution_score))
    )

    risk_index = _clamp_score(
        0.45 * caution_score
        + 0.35 * whale_reversal_risk
        + 0.20 * (0.0 if usability == "USABLE_NOW" else 0.5 if usability == "NEEDS_CONFIRMATION" else 1.0)
    )
    if primary_trade_type == "NO_TRADE":
        risk_posture_class = "DO_NOT_DEPLOY"
    elif risk_index <= 0.25:
        risk_posture_class = "LOW_RISK"
    elif risk_index <= 0.50:
        risk_posture_class = "BALANCED"
    elif risk_index <= 0.70:
        risk_posture_class = "ELEVATED_RISK"
    else:
        risk_posture_class = "HIGH_RISK"

    suggested_bucket_class = {
        "FAST_TRADE": "FAST_BUCKET",
        "RISKY_HIGHER_UPSIDE": "RISKY_BUCKET",
        "WHALE_FOLLOW": "WHALE_BUCKET",
        "SLOW_CONVICTION": "CONVICTION_BUCKET",
        "NO_TRADE": "NO_BUCKET",
    }[primary_trade_type]

    if primary_trade_type == "NO_TRADE" and not decision_selected:
        reason_codes.append("not_selected_in_decision_context")
    if cognition is None:
        reason_codes.append("missing_cognition_context")
    if whale is None:
        reason_codes.append("missing_whale_context")
    if time_to_close_hours is not None and time_to_close_hours <= 24:
        reason_codes.append("very_short_time_to_close")
    if usability == "NEEDS_CONFIRMATION":
        reason_codes.append("needs_confirmation")
    if whale_presence >= 0.60:
        reason_codes.append("strong_whale_presence")

    reason_codes = list(dict.fromkeys(code for code in reason_codes if code))
    reason_text = (
        f"Market {context['market_id']} classified as {primary_trade_type} with confidence={classification_confidence:.2f}, "
        f"risk={risk_posture_class}, cognition_confidence={cognition_confidence:.2f}, caution={caution_score:.2f}, "
        f"whale_alignment={whale_alignment:.2f}, whale_reversal_risk={whale_reversal_risk:.2f}."
    )

    return {
        "primary_trade_type": primary_trade_type,
        "secondary_trade_types": secondary_trade_types,
        "classification_confidence": classification_confidence,
        "risk_posture_class": risk_posture_class,
        "suggested_bucket_class": suggested_bucket_class,
        "reason_codes": reason_codes,
        "reason_text": reason_text,
        "explanation": {
            "market_snapshot": {
                "question": market.get("question"),
                "liquidity": liquidity,
                "time_to_close_hours": round(time_to_close_hours, 5) if time_to_close_hours is not None else None,
                "accepting_orders": market.get("accepting_orders"),
            },
            "decision": {
                "decision_type": decision_type,
                "selected": decision_selected,
                "confidence": round(decision_confidence, 5),
                "expected_edge_proxy": round(expected_edge, 5),
            },
            "cognition": {
                "usability_class": usability,
                "cognition_conclusion_class": cognition_conclusion,
                "overall_confidence_score": round(cognition_confidence, 5),
                "caution_score": round(caution_score, 5),
            },
            "whale": {
                "presence_score": round(whale_presence, 5),
                "conviction_score": round(whale_conviction, 5),
                "alignment_score": round(whale_alignment, 5),
                "reversal_risk": round(whale_reversal_risk, 5),
            },
            "secondary_trade_types": secondary_trade_types,
        },
    }


def _normalize_market_id(market_id: str) -> str:
    market = str(market_id or "").strip()
    if not market:
        raise ValueError("market_id is required")
    return market


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clamp_score(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 5)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 6A trade classification")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--market-ids", nargs="+", help="market ids to classify")
    group.add_argument("--cycle-id", help="classify all markets from a specific cycle")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = TradeClassificationService()
    if args.cycle_id:
        result = service.classify_cycle(args.cycle_id, source_ref=args.source_ref)
    else:
        result = service.classify_markets(
            args.market_ids,
            source_type="manual_market_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Trade classification persistence is unavailable.")
        return 1

    print(
        f"trade_classification_run_id={result.trade_classification_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
