"""
Deterministic adaptive ranking for Stage 4 live selection.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.stage4.universe import UniverseCandidate
from gamma_crawler import hours_remaining

BUCKET_EXECUTION_SCORE = {
    "safe": 6.0,
    "high": 8.0,
    "whale": 10.0,
}


@dataclass(slots=True)
class RankBreakdown:
    market_score: float
    confidence: float
    edge: float
    time: float
    execution: float
    risk_penalty: float


@dataclass(slots=True)
class RankedCandidate:
    candidate: UniverseCandidate
    total_rank: float
    breakdown: RankBreakdown
    reason: str


def _time_score(candidate: UniverseCandidate) -> float:
    remaining = hours_remaining(candidate.market)
    if remaining is None:
        return 5.0
    if remaining <= 0:
        return -4.0
    if remaining <= 6:
        return 3.0
    if remaining <= 48:
        return 9.0
    if remaining <= 24 * 14:
        return 12.0
    if remaining <= 24 * 90:
        return 6.0
    return 2.0


def _risk_penalty(candidate: UniverseCandidate) -> float:
    remaining = hours_remaining(candidate.market)
    penalty = 0.0
    if remaining is not None and remaining > 24 * 180:
        penalty += 4.0
    if candidate.market.liquidity is not None and candidate.market.liquidity < 1000:
        penalty += 3.0
    if candidate.feasible_price >= 0.90 or candidate.feasible_price <= 0.05:
        penalty += 4.0
    return penalty


def rank_candidates(candidates: list[UniverseCandidate]) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        market_score = candidate.item.score * 0.55
        confidence = candidate.recommendation.confidence * 25.0
        edge = min(max(float(candidate.edge_cents or 0.0), 0.0), 25.0) * 0.4
        time_component = _time_score(candidate)
        execution = BUCKET_EXECUTION_SCORE.get(candidate.bucket, 6.0)
        risk_penalty = _risk_penalty(candidate)
        total_rank = round(market_score + confidence + edge + time_component + execution - risk_penalty, 2)
        breakdown = RankBreakdown(
            market_score=round(market_score, 2),
            confidence=round(confidence, 2),
            edge=round(edge, 2),
            time=round(time_component, 2),
            execution=round(execution, 2),
            risk_penalty=round(risk_penalty, 2),
        )
        reason = (
            f"score={breakdown.market_score:.2f} confidence={breakdown.confidence:.2f} "
            f"edge={breakdown.edge:.2f} time={breakdown.time:.2f} execution={breakdown.execution:.2f} "
            f"risk_penalty={breakdown.risk_penalty:.2f}"
        )
        ranked.append(
            RankedCandidate(
                candidate=candidate,
                total_rank=total_rank,
                breakdown=breakdown,
                reason=reason,
            )
        )
    ranked.sort(
        key=lambda item: (
            -item.total_rank,
            -item.candidate.recommendation.confidence,
            -item.candidate.item.score,
            item.candidate.market.market_id,
        )
    )
    return ranked
