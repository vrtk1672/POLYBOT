from __future__ import annotations

import argparse
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.whale_profile import WhaleProfileContract
from app.domain.contracts.whale_profile_run import WhaleProfileRunCloseContract, WhaleProfileRunOpenContract
from app.repositories.whale_events_repository import WhaleEventsRepository
from app.repositories.whale_profile_runs_repository import WhaleProfileRunsRepository
from app.repositories.whale_profiles_repository import WhaleProfilesRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.services.recorders.whale_profile_recorder import WhaleProfileRecorder
from app.services.recorders.whale_profile_run_recorder import WhaleProfileRunRecorder

logger = logging.getLogger(__name__)

PROFILER_VERSION = "phase5b-whale-profiling-v1"
PROFILE_STATUSES = {"PROFILE_READY", "SPARSE_HISTORY", "NOISY", "REVIEW"}


@dataclass(slots=True)
class WhaleProfileRunResult:
    whale_profile_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class WhaleProfilingService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        profiler_version: str = PROFILER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._profiler_version = profiler_version
        self._events = WhaleEventsRepository()
        self._registry = WhaleRegistryRepository()
        self._runs = WhaleProfileRunsRepository()
        self._profiles = WhaleProfilesRepository()
        self._run_recorder = WhaleProfileRunRecorder()
        self._profile_recorder = WhaleProfileRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def profile_active_wallets(
        self,
        *,
        limit: int = 100,
        source_ref: str | None = None,
    ) -> WhaleProfileRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._registry.list_active(conn, limit)
        wallets = [str(row["wallet_address"]) for row in rows]
        return self.profile_wallets(wallets, source_type="active_registry_wallets", source_ref=source_ref or "active_registry")

    def profile_wallets(
        self,
        wallet_addresses: list[str],
        *,
        source_type: str = "wallet_batch",
        source_ref: str | None = None,
    ) -> WhaleProfileRunResult | None:
        if not self.enabled:
            return None
        if not wallet_addresses:
            raise ValueError("at least one wallet_address is required")

        wallets = [_normalize_wallet(wallet) for wallet in wallet_addresses]
        run_id = str(uuid4())
        started_at = datetime.now(UTC)
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    WhaleProfileRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_as_optional_str(source_ref),
                        status="OPEN",
                        profiler_version=self._profiler_version,
                        started_at=started_at,
                        input_count=len(wallets),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "profiler_version": self._profiler_version,
                        },
                    ),
                )
                opened_run = True

                for wallet in wallets:
                    try:
                        registry_row = self._registry.get_by_wallet(conn, wallet)
                        if registry_row is None:
                            raise ValueError(f"whale registry entry not found: {wallet}")
                        event_rows = [dict(row) for row in self._events.list_for_wallet(conn, wallet, 10000)]
                        if not event_rows:
                            raise ValueError(f"no whale events found for wallet: {wallet}")
                        profile_contract = self._build_profile_contract(
                            run_id=run_id,
                            wallet_address=wallet,
                            registry_row=dict(registry_row),
                            event_rows=event_rows,
                        )
                        self._profile_recorder.record(conn, profile_contract)
                        success_count += 1
                    except Exception:
                        logger.exception("whale_profile_wallet_failed wallet=%s", wallet)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    WhaleProfileRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "profiler_version": self._profiler_version,
                            "source_ref": _as_optional_str(source_ref),
                        },
                    ),
                )

            return WhaleProfileRunResult(
                whale_profile_run_id=run_id,
                status=status,
                input_count=len(wallets),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("whale_profile_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        WhaleProfileRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_as_optional_str(source_ref),
                            status="OPEN",
                            profiler_version=self._profiler_version,
                            started_at=started_at,
                            input_count=len(wallets),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    WhaleProfileRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=datetime.now(UTC),
                        success_count=success_count,
                        failure_count=max(1, len(wallets)),
                        metadata_json={"error": str(exc), "profiler_version": self._profiler_version},
                    ),
                )
            return WhaleProfileRunResult(
                whale_profile_run_id=run_id,
                status="FAILED",
                input_count=len(wallets),
                success_count=success_count,
                failure_count=max(1, len(wallets)),
            )

    def _build_profile_contract(
        self,
        *,
        run_id: str,
        wallet_address: str,
        registry_row: dict[str, object],
        event_rows: list[dict[str, object]],
    ) -> WhaleProfileContract:
        metrics = _compute_profile_metrics(event_rows)
        return WhaleProfileContract(
            id=str(uuid4()),
            wallet_address=wallet_address,
            whale_profile_run_id=run_id,
            total_events=metrics["total_events"],
            entry_count=metrics["entry_count"],
            exit_count=metrics["exit_count"],
            reversal_candidate_count=metrics["reversal_candidate_count"],
            unknown_count=metrics["unknown_count"],
            average_size=metrics["average_size"],
            average_notional=metrics["average_notional"],
            largest_size=metrics["largest_size"],
            largest_notional=metrics["largest_notional"],
            active_markets_count=metrics["active_markets_count"],
            market_specialties_json=metrics["market_specialties_json"],
            timing_consistency_score=metrics["timing_consistency_score"],
            noise_score=metrics["noise_score"],
            average_hold_time=metrics["average_hold_time"],
            follow_value_baseline=metrics["follow_value_baseline"],
            profile_status=metrics["profile_status"],
            explanation_json={
                "registry_status": registry_row["registry_status"],
                "last_market_id": registry_row["last_market_id"],
                "metric_context": metrics["explanation"],
            },
            profiler_version=self._profiler_version,
        )


def _compute_profile_metrics(event_rows: list[dict[str, object]]) -> dict[str, object]:
    ordered_rows = sorted(event_rows, key=lambda row: (row["event_timestamp"], row["created_at"]))
    total_events = len(ordered_rows)
    direction_counts = Counter(str(row["event_direction_class"]) for row in ordered_rows)

    sizes = [float(row["size"]) for row in ordered_rows]
    notionals = [float(row["notional"]) for row in ordered_rows if row["notional"] is not None]
    average_size = round(sum(sizes) / total_events, 6)
    average_notional = round(sum(notionals) / len(notionals), 6) if notionals else None
    largest_size = round(max(sizes), 6)
    largest_notional = round(max(notionals), 6) if notionals else None

    market_counter = Counter(str(row["market_id"]) for row in ordered_rows)
    active_markets_count = len(market_counter)
    market_specialties = []
    for market_id, count in market_counter.most_common(3):
        market_specialties.append(
            {
                "market_id": market_id,
                "event_count": count,
                "share": round(count / total_events, 5),
            }
        )

    timing_consistency_score = _compute_timing_consistency_score(ordered_rows)
    noise_score = _compute_noise_score(direction_counts, total_events)
    average_hold_time = _compute_average_hold_time_hours(ordered_rows)
    follow_value_baseline = _compute_follow_value_baseline(
        total_events=total_events,
        average_size=average_size,
        active_markets_count=active_markets_count,
        timing_consistency_score=timing_consistency_score,
        noise_score=noise_score,
    )
    profile_status = _derive_profile_status(
        total_events=total_events,
        timing_consistency_score=timing_consistency_score,
        noise_score=noise_score,
    )

    return {
        "total_events": total_events,
        "entry_count": direction_counts.get("ENTRY", 0),
        "exit_count": direction_counts.get("EXIT", 0),
        "reversal_candidate_count": direction_counts.get("REVERSAL_CANDIDATE", 0),
        "unknown_count": direction_counts.get("UNKNOWN", 0),
        "average_size": average_size,
        "average_notional": average_notional,
        "largest_size": largest_size,
        "largest_notional": largest_notional,
        "active_markets_count": active_markets_count,
        "market_specialties_json": market_specialties,
        "timing_consistency_score": timing_consistency_score,
        "noise_score": noise_score,
        "average_hold_time": average_hold_time,
        "follow_value_baseline": follow_value_baseline,
        "profile_status": profile_status,
        "explanation": {
            "direction_counts": dict(direction_counts),
            "top_markets": market_specialties,
            "hold_time_derived": average_hold_time is not None,
        },
    }


def _compute_timing_consistency_score(event_rows: list[dict[str, object]]) -> float:
    if len(event_rows) < 2:
        return 0.25
    timestamps = [row["event_timestamp"] for row in event_rows]
    intervals = [
        max(1.0, (timestamps[idx] - timestamps[idx - 1]).total_seconds())
        for idx in range(1, len(timestamps))
    ]
    mean_interval = sum(intervals) / len(intervals)
    if mean_interval <= 0:
        return 0.25
    if len(intervals) == 1:
        return 0.7
    variance = sum((interval - mean_interval) ** 2 for interval in intervals) / len(intervals)
    stdev = math.sqrt(variance)
    cv = stdev / mean_interval if mean_interval else 1.0
    return _clamp_score(1.0 - min(1.0, cv))


def _compute_noise_score(direction_counts: Counter[str], total_events: int) -> float:
    unknown_ratio = direction_counts.get("UNKNOWN", 0) / total_events
    reversal_ratio = direction_counts.get("REVERSAL_CANDIDATE", 0) / total_events
    return _clamp_score((unknown_ratio * 0.6) + (reversal_ratio * 0.8))


def _compute_average_hold_time_hours(event_rows: list[dict[str, object]]) -> float | None:
    open_entries: dict[str, list[datetime]] = defaultdict(list)
    hold_durations: list[float] = []

    ordered_rows = sorted(event_rows, key=lambda row: (row["event_timestamp"], row["created_at"]))
    for row in ordered_rows:
        market_id = str(row["market_id"])
        direction = str(row["event_direction_class"])
        timestamp = row["event_timestamp"]
        if direction == "ENTRY":
            open_entries[market_id].append(timestamp)
        elif direction in {"EXIT", "REVERSAL_CANDIDATE"} and open_entries[market_id]:
            entry_time = open_entries[market_id].pop(0)
            hold_hours = max(0.0, (timestamp - entry_time).total_seconds() / 3600.0)
            hold_durations.append(hold_hours)

    if not hold_durations:
        return None
    return round(sum(hold_durations) / len(hold_durations), 6)


def _compute_follow_value_baseline(
    *,
    total_events: int,
    average_size: float,
    active_markets_count: int,
    timing_consistency_score: float,
    noise_score: float,
) -> float:
    event_score = min(1.0, total_events / 6.0)
    size_score = min(1.0, average_size / 2500.0)
    specialization_score = 1.0 / max(1, active_markets_count)
    baseline = (
        (event_score * 0.3)
        + (size_score * 0.25)
        + (timing_consistency_score * 0.25)
        + ((1.0 - noise_score) * 0.15)
        + (specialization_score * 0.05)
    )
    return _clamp_score(baseline)


def _derive_profile_status(
    *,
    total_events: int,
    timing_consistency_score: float,
    noise_score: float,
) -> str:
    if total_events < 2:
        return "SPARSE_HISTORY"
    if noise_score >= 0.55:
        return "NOISY"
    if timing_consistency_score < 0.35:
        return "REVIEW"
    return "PROFILE_READY"


def _normalize_wallet(wallet_address: str) -> str:
    wallet = str(wallet_address or "").strip().lower()
    if not wallet:
        raise ValueError("wallet_address is required")
    return wallet


def _clamp_score(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 5)


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 5B whale profiling")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--wallet-addresses", nargs="+", help="wallet addresses to profile")
    group.add_argument("--all-active-wallets", action="store_true", help="profile active whale registry wallets")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = WhaleProfilingService()
    if args.all_active_wallets:
        result = service.profile_active_wallets(source_ref=args.source_ref)
    else:
        result = service.profile_wallets(args.wallet_addresses, source_type="manual_wallet_batch", source_ref=args.source_ref)

    if result is None:
        print("Whale profiling persistence is unavailable.")
        return 1

    print(
        f"whale_profile_run_id={result.whale_profile_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
