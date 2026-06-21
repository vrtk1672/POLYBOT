from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WhaleProfileContract:
    id: str
    wallet_address: str
    whale_profile_run_id: str
    total_events: int
    entry_count: int
    exit_count: int
    reversal_candidate_count: int
    unknown_count: int
    average_size: float
    average_notional: float | None
    largest_size: float
    largest_notional: float | None
    active_markets_count: int
    market_specialties_json: list[dict[str, object]] = field(default_factory=list)
    timing_consistency_score: float = 0.0
    noise_score: float = 0.0
    average_hold_time: float | None = None
    follow_value_baseline: float = 0.0
    profile_status: str = "SPARSE_HISTORY"
    explanation_json: dict[str, object] = field(default_factory=dict)
    profiler_version: str = ""
