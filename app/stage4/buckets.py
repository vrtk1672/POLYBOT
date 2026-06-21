"""
Configured bucket foundation for Stage 4 sizing.
"""

from __future__ import annotations

from dataclasses import dataclass


BUCKET_WEIGHTS = {
    "safe": 0.05,
    "high": 0.10,
    "whale": 0.15,
    "reserve": 0.70,
}


@dataclass(slots=True)
class BucketTargets:
    safe: float
    high: float
    whale: float
    reserve: float


def compute_bucket_targets(total_balance: float) -> BucketTargets:
    total = max(total_balance, 0.0)
    return BucketTargets(
        safe=round(total * BUCKET_WEIGHTS["safe"], 2),
        high=round(total * BUCKET_WEIGHTS["high"], 2),
        whale=round(total * BUCKET_WEIGHTS["whale"], 2),
        reserve=round(total * BUCKET_WEIGHTS["reserve"], 2),
    )


def recommended_bucket_notional(
    total_balance: float,
    bucket: str,
    *,
    max_order_usd: float | None = None,
) -> float:
    targets = compute_bucket_targets(total_balance)
    amount = {
        "safe": targets.safe,
        "high": targets.high,
        "whale": targets.whale,
        "reserve": targets.reserve,
    }.get(bucket, targets.safe)
    if max_order_usd is not None:
        amount = min(amount, max_order_usd)
    return round(max(amount, 0.0), 2)
