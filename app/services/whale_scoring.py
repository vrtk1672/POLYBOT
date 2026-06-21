from __future__ import annotations

import argparse
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.whale_market_score import WhaleMarketScoreContract
from app.domain.contracts.whale_scoring_run import WhaleScoringRunCloseContract, WhaleScoringRunOpenContract
from app.repositories.whale_categories_repository import WhaleCategoriesRepository
from app.repositories.whale_events_repository import WhaleEventsRepository
from app.repositories.whale_market_scores_repository import WhaleMarketScoresRepository
from app.repositories.whale_profiles_repository import WhaleProfilesRepository
from app.repositories.whale_scoring_runs_repository import WhaleScoringRunsRepository
from app.services.recorders.whale_market_score_recorder import WhaleMarketScoreRecorder
from app.services.recorders.whale_scoring_run_recorder import WhaleScoringRunRecorder

logger = logging.getLogger(__name__)

SCORER_VERSION = "phase5d-whale-scoring-v1"
SMART_WHALE_CATEGORIES = {"SMART_WHALE", "COPY_WORTHY", "SPORTS_SPECIALIST", "POLITICS_SPECIALIST", "EVENT_SNIPER"}
NOISY_WHALE_CATEGORIES = {"NOISY_WHALE", "LATE_CHASER"}
DEFAULT_WINDOW_HOURS = 168


@dataclass(slots=True)
class WhaleScoringRunResult:
    whale_scoring_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class WhaleScoringService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        scorer_version: str = SCORER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._scorer_version = scorer_version
        self._runs = WhaleScoringRunsRepository()
        self._scores = WhaleMarketScoresRepository()
        self._events = WhaleEventsRepository()
        self._profiles = WhaleProfilesRepository()
        self._categories = WhaleCategoriesRepository()
        self._run_recorder = WhaleScoringRunRecorder()
        self._score_recorder = WhaleMarketScoreRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def score_recent_markets(
        self,
        *,
        window_hours: int = DEFAULT_WINDOW_HOURS,
        limit_markets: int | None = None,
        source_ref: str | None = None,
    ) -> WhaleScoringRunResult | None:
        if not self.enabled:
            return None
        window_end = _utc_now()
        window_start = window_end - timedelta(hours=max(1, int(window_hours)))
        with self._factory.connect() as conn:
            market_ids = self._events.list_recent_markets(
                conn,
                window_start=window_start,
                window_end=window_end,
                limit=limit_markets,
            )
        normalized_market_ids: list[str] = []
        dropped_market_ids = 0
        for market_id in market_ids:
            try:
                normalized_market_ids.append(_normalize_market_id(market_id))
            except ValueError:
                dropped_market_ids += 1
        if dropped_market_ids:
            logger.warning("whale_recent_markets_dropped_invalid_ids count=%s", dropped_market_ids)
        if not normalized_market_ids:
            logger.info(
                "whale_recent_markets_noop window_hours=%s limit_markets=%s reason=no_recent_market_ids",
                int(window_hours),
                limit_markets,
            )
            return None
        return self.score_markets(
            normalized_market_ids,
            window_start=window_start,
            window_end=window_end,
            source_type="recent_market_window",
            source_ref=source_ref or f"window:{int(window_hours)}h",
        )

    def score_markets(
        self,
        market_ids: list[str],
        *,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        source_type: str = "market_batch",
        source_ref: str | None = None,
    ) -> WhaleScoringRunResult | None:
        if not self.enabled:
            return None
        if not market_ids:
            raise ValueError("at least one market_id is required")

        normalized_market_ids = [_normalize_market_id(market_id) for market_id in market_ids]
        scoring_window_end = window_end or _utc_now()
        scoring_window_start = window_start or (scoring_window_end - timedelta(hours=DEFAULT_WINDOW_HOURS))
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    WhaleScoringRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_as_optional_str(source_ref),
                        status="OPEN",
                        scorer_version=self._scorer_version,
                        started_at=started_at,
                        input_count=len(normalized_market_ids),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "scorer_version": self._scorer_version,
                            "window_start": scoring_window_start.isoformat(),
                            "window_end": scoring_window_end.isoformat(),
                        },
                    ),
                )
                opened_run = True

                for market_id in normalized_market_ids:
                    try:
                        events = self._events.list_for_market_in_window(
                            conn,
                            market_id=market_id,
                            window_start=scoring_window_start,
                            window_end=scoring_window_end,
                        )
                        if not events:
                            raise ValueError(f"no whale events found in scoring window for market: {market_id}")
                        score = self._score_market(events, conn=conn, market_id=market_id, window_start=scoring_window_start, window_end=scoring_window_end)
                        contract = WhaleMarketScoreContract(
                            id=str(uuid4()),
                            whale_scoring_run_id=run_id,
                            market_id=market_id,
                            scoring_window_start=scoring_window_start,
                            scoring_window_end=scoring_window_end,
                            whale_presence_score=score["whale_presence_score"],
                            whale_conviction_score=score["whale_conviction_score"],
                            smart_whale_alignment_score=score["smart_whale_alignment_score"],
                            whale_reversal_risk=score["whale_reversal_risk"],
                            supporting_wallet_count=score["supporting_wallet_count"],
                            top_supporting_wallets_json=score["top_supporting_wallets"],
                            category_mix_json=score["category_mix"],
                            scoring_reason_codes_json=score["reason_codes"],
                            scoring_reason_text=score["reason_text"],
                            explanation_json=score["explanation"],
                            scorer_version=self._scorer_version,
                        )
                        self._score_recorder.record(conn, contract)
                        success_count += 1
                    except Exception:
                        logger.exception("whale_score_market_failed market_id=%s", market_id)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    WhaleScoringRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "scorer_version": self._scorer_version,
                            "source_ref": _as_optional_str(source_ref),
                            "window_start": scoring_window_start.isoformat(),
                            "window_end": scoring_window_end.isoformat(),
                        },
                    ),
                )

            return WhaleScoringRunResult(
                whale_scoring_run_id=run_id,
                status=status,
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("whale_scoring_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        WhaleScoringRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_as_optional_str(source_ref),
                            status="OPEN",
                            scorer_version=self._scorer_version,
                            started_at=started_at,
                            input_count=len(normalized_market_ids),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    WhaleScoringRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(normalized_market_ids)),
                        metadata_json={"error": str(exc), "scorer_version": self._scorer_version},
                    ),
                )
            return WhaleScoringRunResult(
                whale_scoring_run_id=run_id,
                status="FAILED",
                input_count=len(normalized_market_ids),
                success_count=success_count,
                failure_count=max(1, len(normalized_market_ids)),
            )

    def _score_market(
        self,
        events: list[dict[str, object]],
        *,
        conn,
        market_id: str,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, object]:
        event_rows = [dict(row) for row in events]
        wallet_stats: dict[str, dict[str, object]] = {}
        direction_counts: Counter[str] = Counter()
        category_mix: Counter[str] = Counter()
        total_size = 0.0
        total_notional = 0.0
        notional_count = 0
        reversal_event_count = 0

        for row in event_rows:
            wallet = str(row["wallet_address"]).lower()
            stats = wallet_stats.setdefault(
                wallet,
                {
                    "wallet_address": wallet,
                    "event_count": 0,
                    "total_size": 0.0,
                    "largest_size": 0.0,
                    "total_notional": 0.0,
                    "notional_count": 0,
                },
            )
            size = float(row["size"])
            notional_value = row["notional"]
            stats["event_count"] += 1
            stats["total_size"] += size
            stats["largest_size"] = max(float(stats["largest_size"]), size)
            total_size += size
            if notional_value is not None:
                stats["total_notional"] += float(notional_value)
                stats["notional_count"] += 1
                total_notional += float(notional_value)
                notional_count += 1

            direction = str(row["event_direction_class"])
            direction_counts[direction] += 1
            if direction == "REVERSAL_CANDIDATE":
                reversal_event_count += 1

        supporting_wallets: list[dict[str, object]] = []
        smart_weight = 0.0
        noisy_weight = 0.0
        total_follow_weight = 0.0
        noisy_wallet_count = 0

        for wallet, stats in wallet_stats.items():
            profile_row = self._profiles.get_latest_by_wallet(conn, wallet)
            category_row = self._categories.get_latest_by_wallet(conn, wallet)
            if profile_row is None or category_row is None:
                raise ValueError(f"wallet scoring context incomplete for {wallet}")
            profile = dict(profile_row)
            category = dict(category_row)
            primary_category = str(category["primary_category"])
            follow_value = float(profile["follow_value_baseline"])
            total_follow_weight += max(0.05, follow_value)
            if primary_category in SMART_WHALE_CATEGORIES:
                smart_weight += max(0.1, follow_value)
            if primary_category in NOISY_WHALE_CATEGORIES:
                noisy_weight += max(0.1, 1.0 - follow_value + float(profile["noise_score"]))
                noisy_wallet_count += 1
            category_mix[primary_category] += 1
            supporting_wallets.append(
                {
                    "wallet_address": wallet,
                    "primary_category": primary_category,
                    "follow_value_baseline": round(follow_value, 5),
                    "event_count_on_market": int(stats["event_count"]),
                    "total_size_on_market": round(float(stats["total_size"]), 5),
                    "largest_size_on_market": round(float(stats["largest_size"]), 5),
                }
            )

        wallet_count = len(wallet_stats)
        event_count = len(event_rows)
        average_size = total_size / max(1, event_count)
        average_notional = total_notional / notional_count if notional_count else None
        dominant_direction_ratio = max(direction_counts.values()) / max(1, event_count)
        reversal_ratio = reversal_event_count / max(1, event_count)
        mixed_direction_ratio = 1.0 - dominant_direction_ratio

        presence_wallet_component = min(1.0, wallet_count / 4.0)
        presence_event_component = min(1.0, event_count / 6.0)
        presence_size_component = min(1.0, average_size / 2500.0)
        presence_notional_component = min(1.0, (average_notional or 0.0) / 25000.0)
        whale_presence_score = _clamp_score(
            0.35 * presence_wallet_component
            + 0.20 * presence_event_component
            + 0.30 * presence_size_component
            + 0.15 * presence_notional_component
        )

        size_strength = min(1.0, max(float(stats["largest_size"]) for stats in wallet_stats.values()) / 3000.0)
        follow_support = (
            sum(float(self._profiles.get_latest_by_wallet(conn, wallet)["follow_value_baseline"]) for wallet in wallet_stats) / wallet_count
            if wallet_count
            else 0.0
        )
        whale_conviction_score = _clamp_score(
            0.45 * dominant_direction_ratio
            + 0.30 * size_strength
            + 0.15 * (1.0 - reversal_ratio)
            + 0.10 * follow_support
        )

        smart_share = smart_weight / max(0.1, total_follow_weight)
        noisy_share = noisy_weight / max(0.1, total_follow_weight)
        specialist_bonus = min(0.15, sum(0.05 for category in category_mix if category.endswith("_SPECIALIST")))
        smart_whale_alignment_score = _clamp_score((smart_share * 0.75) + ((1.0 - noisy_share) * 0.20) + specialist_bonus)

        noisy_wallet_ratio = noisy_wallet_count / max(1, wallet_count)
        whale_reversal_risk = _clamp_score(
            0.45 * reversal_ratio
            + 0.35 * noisy_wallet_ratio
            + 0.20 * mixed_direction_ratio
        )

        top_supporting_wallets = sorted(
            supporting_wallets,
            key=lambda row: (
                float(row["total_size_on_market"]),
                float(row["follow_value_baseline"]),
                int(row["event_count_on_market"]),
            ),
            reverse=True,
        )[:3]

        category_mix_json = {
            category: {
                "wallet_count": count,
                "share": round(count / max(1, wallet_count), 5),
            }
            for category, count in category_mix.items()
        }

        reason_codes: list[str] = []
        if whale_presence_score >= 0.60:
            reason_codes.append("strong_presence")
        if whale_conviction_score >= 0.60:
            reason_codes.append("strong_conviction")
        if smart_whale_alignment_score >= 0.60:
            reason_codes.append("smart_wallet_support")
        if whale_reversal_risk >= 0.35 or reversal_ratio >= 0.4:
            reason_codes.append("elevated_reversal_risk")
        if noisy_wallet_ratio >= 0.4:
            reason_codes.append("noisy_wallet_mix")
        if wallet_count <= 1 or event_count <= 2:
            reason_codes.append("sparse_market_support")
        if any(category.endswith("_SPECIALIST") for category in category_mix):
            reason_codes.append("specialist_support")
        if not reason_codes:
            reason_codes.append("balanced_whale_signal")

        reason_text = (
            f"Market {market_id} has {wallet_count} supporting whale wallet(s) across {event_count} event(s), "
            f"presence={whale_presence_score:.2f}, conviction={whale_conviction_score:.2f}, "
            f"alignment={smart_whale_alignment_score:.2f}, reversal_risk={whale_reversal_risk:.2f}."
        )

        return {
            "whale_presence_score": whale_presence_score,
            "whale_conviction_score": whale_conviction_score,
            "smart_whale_alignment_score": smart_whale_alignment_score,
            "whale_reversal_risk": whale_reversal_risk,
            "supporting_wallet_count": wallet_count,
            "top_supporting_wallets": top_supporting_wallets,
            "category_mix": category_mix_json,
            "reason_codes": reason_codes,
            "reason_text": reason_text,
            "explanation": {
                "scoring_window": {
                    "start": window_start.isoformat(),
                    "end": window_end.isoformat(),
                },
                "event_count": event_count,
                "direction_counts": dict(direction_counts),
                "wallet_count": wallet_count,
                "average_size": round(average_size, 5),
                "average_notional": round(average_notional, 5) if average_notional is not None else None,
                "dominant_direction_ratio": round(dominant_direction_ratio, 5),
                "reversal_ratio": round(reversal_ratio, 5),
                "mixed_direction_ratio": round(mixed_direction_ratio, 5),
                "noisy_wallet_ratio": round(noisy_wallet_ratio, 5),
                "smart_share": round(smart_share, 5),
                "top_supporting_wallets": top_supporting_wallets,
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
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 5D whale scoring")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--market-ids", nargs="+", help="market ids to score")
    group.add_argument("--recent-markets", action="store_true", help="score recent markets from whale events")
    parser.add_argument("--window-hours", type=int, default=DEFAULT_WINDOW_HOURS, help="scoring window in hours")
    parser.add_argument("--limit-markets", type=int, default=None, help="optional recent market limit")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = WhaleScoringService()
    if args.recent_markets:
        result = service.score_recent_markets(
            window_hours=args.window_hours,
            limit_markets=args.limit_markets,
            source_ref=args.source_ref,
        )
    else:
        window_end = _utc_now()
        window_start = window_end - timedelta(hours=max(1, int(args.window_hours)))
        result = service.score_markets(
            args.market_ids,
            window_start=window_start,
            window_end=window_end,
            source_type="manual_market_batch",
            source_ref=args.source_ref,
        )

    if result is None:
        print("Whale scoring persistence is unavailable.")
        return 1

    print(
        f"whale_scoring_run_id={result.whale_scoring_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
