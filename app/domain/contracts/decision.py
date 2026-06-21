from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DecisionLedgerContract:
    id: str
    cycle_id: str
    market_snapshot_id: int
    ranking_snapshot_id: int | None
    market_id: str
    decision_type: str
    selected: bool
    reason: str
    confidence: float | None
    trade_type: str | None
    bucket_type: str | None
    expected_edge_proxy: float | None
    invalidation_rules: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
