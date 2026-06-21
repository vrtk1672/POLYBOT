from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class WhaleMarketScoreContract:
    id: str
    whale_scoring_run_id: str
    market_id: str
    scoring_window_start: datetime | None
    scoring_window_end: datetime | None
    whale_presence_score: float
    whale_conviction_score: float
    smart_whale_alignment_score: float
    whale_reversal_risk: float
    supporting_wallet_count: int
    top_supporting_wallets_json: list[dict[str, object]] = field(default_factory=list)
    category_mix_json: dict[str, object] = field(default_factory=dict)
    scoring_reason_codes_json: list[str] = field(default_factory=list)
    scoring_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    scorer_version: str = ""
