from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from uuid import uuid4

from app.db.config import DatabaseSettings, get_database_settings
from app.db.connection import DatabaseConnectionFactory
from app.domain.contracts.whale_category import WhaleCategoryContract
from app.domain.contracts.whale_category_run import WhaleCategoryRunCloseContract, WhaleCategoryRunOpenContract
from app.repositories.whale_categories_repository import WhaleCategoriesRepository
from app.repositories.whale_category_runs_repository import WhaleCategoryRunsRepository
from app.repositories.whale_profiles_repository import WhaleProfilesRepository
from app.repositories.whale_registry_repository import WhaleRegistryRepository
from app.services.recorders.whale_category_recorder import WhaleCategoryRecorder
from app.services.recorders.whale_category_run_recorder import WhaleCategoryRunRecorder

logger = logging.getLogger(__name__)

CATEGORIZER_VERSION = "phase5c-whale-categories-v1"
PRIMARY_CATEGORIES = {
    "SMART_WHALE",
    "NOISY_WHALE",
    "MOMENTUM_WHALE",
    "COPY_WORTHY",
    "SPORTS_SPECIALIST",
    "POLITICS_SPECIALIST",
    "EVENT_SNIPER",
    "LATE_CHASER",
    "UNCLASSIFIED",
}

SPORTS_MARKET_KEYWORDS = {"sport", "match", "team", "goal", "psg", "fc", "nba", "nfl", "mlb"}
POLITICS_MARKET_KEYWORDS = {"election", "senate", "president", "minister", "parliament", "policy", "vote"}


@dataclass(slots=True)
class WhaleCategoryRunResult:
    whale_category_run_id: str
    status: str
    input_count: int
    success_count: int
    failure_count: int


class WhaleCategoryService:
    def __init__(
        self,
        settings: DatabaseSettings | None = None,
        connection_factory: DatabaseConnectionFactory | None = None,
        categorizer_version: str = CATEGORIZER_VERSION,
    ) -> None:
        self._settings = settings or get_database_settings()
        self._factory = connection_factory or DatabaseConnectionFactory(self._settings)
        self._categorizer_version = categorizer_version
        self._runs = WhaleCategoryRunsRepository()
        self._categories = WhaleCategoriesRepository()
        self._profiles = WhaleProfilesRepository()
        self._registry = WhaleRegistryRepository()
        self._run_recorder = WhaleCategoryRunRecorder()
        self._category_recorder = WhaleCategoryRecorder()

    @property
    def enabled(self) -> bool:
        return self._factory.enabled

    def categorize_active_wallets(
        self,
        *,
        limit: int = 100,
        source_ref: str | None = None,
    ) -> WhaleCategoryRunResult | None:
        if not self.enabled:
            return None
        with self._factory.connect() as conn:
            rows = self._registry.list_active(conn, limit)
        wallets = [str(row["wallet_address"]) for row in rows]
        return self.categorize_wallets(wallets, source_type="active_registry_wallets", source_ref=source_ref or "active_registry")

    def categorize_wallets(
        self,
        wallet_addresses: list[str],
        *,
        source_type: str = "wallet_batch",
        source_ref: str | None = None,
    ) -> WhaleCategoryRunResult | None:
        if not self.enabled:
            return None
        if not wallet_addresses:
            raise ValueError("at least one wallet_address is required")

        wallets = [_normalize_wallet(wallet) for wallet in wallet_addresses]
        run_id = str(uuid4())
        started_at = _utc_now()
        success_count = 0
        failure_count = 0
        opened_run = False

        try:
            with self._factory.connect() as conn, conn.transaction():
                self._run_recorder.open_run(
                    conn,
                    WhaleCategoryRunOpenContract(
                        id=run_id,
                        source_type=source_type,
                        source_ref=_as_optional_str(source_ref),
                        status="OPEN",
                        categorizer_version=self._categorizer_version,
                        started_at=started_at,
                        input_count=len(wallets),
                        metadata_json={
                            "source_ref": _as_optional_str(source_ref),
                            "categorizer_version": self._categorizer_version,
                        },
                    ),
                )
                opened_run = True

                for wallet in wallets:
                    try:
                        profile_row = self._profiles.get_latest_by_wallet(conn, wallet)
                        if profile_row is None:
                            raise ValueError(f"whale profile not found: {wallet}")
                        category = _categorize_profile(dict(profile_row))
                        contract = WhaleCategoryContract(
                            id=str(uuid4()),
                            wallet_address=wallet,
                            whale_profile_id=str(profile_row["id"]),
                            whale_category_run_id=run_id,
                            primary_category=category["primary_category"],
                            secondary_categories_json=category["secondary_categories"],
                            category_confidence=category["category_confidence"],
                            specialization_context_json=category["specialization_context"],
                            category_reason_codes_json=category["reason_codes"],
                            category_reason_text=category["reason_text"],
                            explanation_json=category["explanation"],
                            categorizer_version=self._categorizer_version,
                        )
                        self._category_recorder.record(conn, contract)
                        success_count += 1
                    except Exception:
                        logger.exception("whale_category_wallet_failed wallet=%s", wallet)
                        failure_count += 1

                status = "COMPLETED" if failure_count == 0 else "COMPLETED_WITH_ERRORS"
                self._run_recorder.close_run(
                    conn,
                    WhaleCategoryRunCloseContract(
                        id=run_id,
                        status=status,
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=failure_count,
                        metadata_json={
                            "categorizer_version": self._categorizer_version,
                            "source_ref": _as_optional_str(source_ref),
                        },
                    ),
                )

            return WhaleCategoryRunResult(
                whale_category_run_id=run_id,
                status=status,
                input_count=len(wallets),
                success_count=success_count,
                failure_count=failure_count,
            )
        except Exception as exc:
            logger.exception("whale_category_run_failed run_id=%s", run_id)
            with self._factory.connect() as conn, conn.transaction():
                if not opened_run:
                    self._run_recorder.open_run(
                        conn,
                        WhaleCategoryRunOpenContract(
                            id=run_id,
                            source_type=source_type,
                            source_ref=_as_optional_str(source_ref),
                            status="OPEN",
                            categorizer_version=self._categorizer_version,
                            started_at=started_at,
                            input_count=len(wallets),
                            metadata_json={"source_ref": _as_optional_str(source_ref)},
                        ),
                    )
                self._run_recorder.close_run(
                    conn,
                    WhaleCategoryRunCloseContract(
                        id=run_id,
                        status="FAILED",
                        ended_at=_utc_now(),
                        success_count=success_count,
                        failure_count=max(1, len(wallets)),
                        metadata_json={"error": str(exc), "categorizer_version": self._categorizer_version},
                    ),
                )
            return WhaleCategoryRunResult(
                whale_category_run_id=run_id,
                status="FAILED",
                input_count=len(wallets),
                success_count=success_count,
                failure_count=max(1, len(wallets)),
            )


def _categorize_profile(profile: dict[str, object]) -> dict[str, object]:
    total_events = int(profile["total_events"])
    follow_value = float(profile["follow_value_baseline"])
    timing = float(profile["timing_consistency_score"])
    noise = float(profile["noise_score"])
    entry_count = int(profile["entry_count"])
    exit_count = int(profile["exit_count"])
    reversal_count = int(profile["reversal_candidate_count"])
    active_markets = int(profile["active_markets_count"])
    profile_status = str(profile["profile_status"])
    specialties = list(profile["market_specialties_json"] or [])

    specialization = _derive_specialization(specialties)
    primary = "UNCLASSIFIED"
    reason_codes: list[str] = []

    if profile_status == "SPARSE_HISTORY" or total_events < 2:
        primary = "UNCLASSIFIED"
        reason_codes.append("sparse_history")
    elif noise >= 0.55:
        primary = "NOISY_WHALE"
        reason_codes.append("high_noise")
    elif specialization == "SPORTS_SPECIALIST":
        primary = "SPORTS_SPECIALIST"
        reason_codes.append("sports_specialization")
    elif specialization == "POLITICS_SPECIALIST":
        primary = "POLITICS_SPECIALIST"
        reason_codes.append("politics_specialization")
    elif (
        entry_count >= max(2, exit_count)
        and (
            timing < 0.45
            or (exit_count == 0 and active_markets >= 3 and timing < 0.8)
        )
    ):
        primary = "LATE_CHASER"
        reason_codes.append("entry_heavy_weak_timing")
    elif follow_value >= 0.72 and timing >= 0.65 and noise <= 0.25 and active_markets <= 2:
        primary = "SMART_WHALE"
        reason_codes.append("high_follow_value")
        reason_codes.append("low_noise_consistent")
    elif follow_value >= 0.62 and noise <= 0.30:
        primary = "COPY_WORTHY"
        reason_codes.append("copy_worthy_baseline")
    elif reversal_count >= 1 and timing >= 0.55:
        primary = "EVENT_SNIPER"
        reason_codes.append("reversal_with_timing")
    elif entry_count > exit_count and reversal_count >= 1:
        primary = "MOMENTUM_WHALE"
        reason_codes.append("entry_heavy_reversal")
    else:
        primary = "UNCLASSIFIED"
        reason_codes.append("insufficient_specific_signal")

    secondary: list[str] = []
    if specialization and specialization != primary:
        secondary.append(specialization)
    if follow_value >= 0.62 and noise <= 0.30 and primary != "COPY_WORTHY":
        secondary.append("COPY_WORTHY")
    if primary != "NOISY_WHALE" and noise >= 0.45:
        secondary.append("NOISY_WHALE")
    if reversal_count >= 1 and timing >= 0.55 and primary != "EVENT_SNIPER":
        secondary.append("EVENT_SNIPER")
    if entry_count > exit_count and reversal_count >= 1 and primary != "MOMENTUM_WHALE":
        secondary.append("MOMENTUM_WHALE")
    secondary = list(dict.fromkeys(category for category in secondary if category in PRIMARY_CATEGORIES and category != primary))

    confidence = _compute_category_confidence(
        primary_category=primary,
        follow_value=follow_value,
        timing=timing,
        noise=noise,
        total_events=total_events,
        specialization=specialization,
    )

    reason_text = _build_reason_text(
        primary_category=primary,
        follow_value=follow_value,
        timing=timing,
        noise=noise,
        total_events=total_events,
        specialization=specialization,
    )

    return {
        "primary_category": primary,
        "secondary_categories": secondary,
        "category_confidence": confidence,
        "specialization_context": {
            "specialization_category": specialization,
            "market_specialties": specialties,
        },
        "reason_codes": reason_codes,
        "reason_text": reason_text,
        "explanation": {
            "profile_metrics": {
                "total_events": total_events,
                "entry_count": entry_count,
                "exit_count": exit_count,
                "reversal_candidate_count": reversal_count,
                "active_markets_count": active_markets,
                "follow_value_baseline": follow_value,
                "timing_consistency_score": timing,
                "noise_score": noise,
            },
            "secondary_categories": secondary,
            "specialization": specialization,
        },
    }


def _derive_specialization(specialties: list[dict[str, object]]) -> str | None:
    if not specialties:
        return None
    top = specialties[0]
    top_market = str(top.get("market_id") or "").lower()
    share = float(top.get("share") or 0.0)
    if share < 0.5:
        return None
    if any(keyword in top_market for keyword in SPORTS_MARKET_KEYWORDS):
        return "SPORTS_SPECIALIST"
    if any(keyword in top_market for keyword in POLITICS_MARKET_KEYWORDS):
        return "POLITICS_SPECIALIST"
    return None


def _compute_category_confidence(
    *,
    primary_category: str,
    follow_value: float,
    timing: float,
    noise: float,
    total_events: int,
    specialization: str | None,
) -> float:
    event_support = min(1.0, total_events / 5.0)
    base = 0.35 + (event_support * 0.2)
    if primary_category in {"SMART_WHALE", "COPY_WORTHY"}:
        base += (follow_value * 0.25) + (timing * 0.15) + ((1.0 - noise) * 0.1)
    elif primary_category == "NOISY_WHALE":
        base += (noise * 0.35)
    elif primary_category in {"SPORTS_SPECIALIST", "POLITICS_SPECIALIST"}:
        base += 0.2 + (0.1 if specialization is not None else 0.0)
    elif primary_category in {"EVENT_SNIPER", "MOMENTUM_WHALE", "LATE_CHASER"}:
        base += (timing * 0.1) + ((1.0 - noise) * 0.05)
    return _clamp_score(base)


def _build_reason_text(
    *,
    primary_category: str,
    follow_value: float,
    timing: float,
    noise: float,
    total_events: int,
    specialization: str | None,
) -> str:
    if primary_category == "SMART_WHALE":
        return "High follow value, strong timing consistency, and low noise point to a disciplined whale profile."
    if primary_category == "COPY_WORTHY":
        return "Follow value is strong enough and noise is contained, making this wallet worth monitoring."
    if primary_category == "NOISY_WHALE":
        return "Noise and reversal uncertainty dominate the wallet history, reducing trust in its signal quality."
    if primary_category in {"SPORTS_SPECIALIST", "POLITICS_SPECIALIST"}:
        return f"Wallet activity clusters strongly around {specialization.lower().replace('_', ' ')} markets."
    if primary_category == "EVENT_SNIPER":
        return "Reversal-aware activity with decent timing suggests a fast event-driven whale."
    if primary_category == "MOMENTUM_WHALE":
        return "Entry-heavy behavior with reversal pressure suggests a momentum-oriented whale pattern."
    if primary_category == "LATE_CHASER":
        return "Entry-heavy behavior with weak timing consistency suggests reactive late chasing."
    return (
        f"Evidence is still limited or mixed: total_events={total_events}, "
        f"follow_value={follow_value:.2f}, timing={timing:.2f}, noise={noise:.2f}."
    )


def _normalize_wallet(wallet_address: str) -> str:
    wallet = str(wallet_address or "").strip().lower()
    if not wallet:
        raise ValueError("wallet_address is required")
    return wallet


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clamp_score(value: float) -> float:
    return round(min(1.0, max(0.0, float(value))), 5)


def _utc_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run POLYBOT Phase 5C whale categorization")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--wallet-addresses", nargs="+", help="wallet addresses to categorize")
    group.add_argument("--all-active-wallets", action="store_true", help="categorize active whale registry wallets")
    parser.add_argument("--source-ref", default=None, help="optional source reference label")
    args = parser.parse_args(argv)

    service = WhaleCategoryService()
    if args.all_active_wallets:
        result = service.categorize_active_wallets(source_ref=args.source_ref)
    else:
        result = service.categorize_wallets(args.wallet_addresses, source_type="manual_wallet_batch", source_ref=args.source_ref)

    if result is None:
        print("Whale categorization persistence is unavailable.")
        return 1

    print(
        f"whale_category_run_id={result.whale_category_run_id} "
        f"status={result.status} "
        f"input={result.input_count} "
        f"success={result.success_count} "
        f"failure={result.failure_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
