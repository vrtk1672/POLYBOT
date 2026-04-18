"""
Execution policy checks for the adaptive Stage 4 selector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.stage4.config import Stage4Settings
from app.stage4.ranking import RankedCandidate


@dataclass(slots=True)
class ExecutionPolicyDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _extract_market_id(order: dict[str, Any]) -> str | None:
    for key in ("market_id", "market", "marketId"):
        value = order.get(key)
        if value:
            return str(value)
    return None


def _extract_created_at(order: dict[str, Any]) -> datetime | None:
    for key in ("createdAt", "created_at"):
        value = order.get(key)
        if not value:
            continue
        try:
            normalized = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(normalized)
        except ValueError:
            continue
    return None


def evaluate_execution_policy(
    candidate: RankedCandidate,
    *,
    open_orders: list[dict[str, Any]],
    settings: Stage4Settings,
    open_orders_error: str | None = None,
    now: datetime | None = None,
) -> ExecutionPolicyDecision:
    reasons: list[str] = []
    current_time = now or datetime.now(UTC)

    if candidate.candidate.recommendation.confidence < settings.live_min_confidence:
        reasons.append(
            f"confidence {candidate.candidate.recommendation.confidence:.2f} is below LIVE_MIN_CONFIDENCE {settings.live_min_confidence:.2f}"
        )
    if candidate.total_rank < settings.live_min_total_rank:
        reasons.append(
            f"total rank {candidate.total_rank:.2f} is below LIVE_MIN_TOTAL_RANK {settings.live_min_total_rank:.2f}"
        )
    if open_orders_error:
        reasons.append(f"open order inspection failed: {open_orders_error}")
        return ExecutionPolicyDecision(False, reasons)

    if len(open_orders) >= settings.live_max_open_positions:
        reasons.append(
            f"open orders {len(open_orders)} meet/exceed LIVE_MAX_OPEN_POSITIONS {settings.live_max_open_positions}"
        )

    same_market_count = 0
    latest_open_order_at: datetime | None = None
    for order in open_orders:
        market_id = _extract_market_id(order)
        created_at = _extract_created_at(order)
        if created_at and (latest_open_order_at is None or created_at > latest_open_order_at):
            latest_open_order_at = created_at
        if market_id == candidate.candidate.market.market_id:
            same_market_count += 1

    if same_market_count >= settings.live_max_same_market_exposure:
        reasons.append(
            f"same-market exposure {same_market_count} meets/exceeds LIVE_MAX_SAME_MARKET_EXPOSURE {settings.live_max_same_market_exposure}"
        )

    if settings.live_cooldown_seconds > 0 and latest_open_order_at is not None:
        elapsed = (current_time - latest_open_order_at.astimezone(UTC)).total_seconds()
        if elapsed < settings.live_cooldown_seconds:
            reasons.append(
                f"cooldown active: {elapsed:.0f}s elapsed, need {settings.live_cooldown_seconds}s"
            )

    return ExecutionPolicyDecision(allowed=not reasons, reasons=reasons)
