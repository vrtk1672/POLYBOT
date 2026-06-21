from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PaperSignalContract:
    id: str
    paper_run_id: str
    cycle_id: str | None
    market_id: str
    decision_id: str | None
    signal_type: str
    intended_outcome: str | None
    trade_type: str | None
    bucket_type: str | None
    confidence: float | None
    expected_edge_proxy: float | None
    intended_price: float | None
    intended_size: float | None
    guard_result: str
    reason_code: str
    reason_text: str
    payload_json: dict[str, object] = field(default_factory=dict)
