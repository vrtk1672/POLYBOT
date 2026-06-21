from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ShadowOrderContract:
    id: str
    shadow_run_id: str
    cycle_id: str | None
    decision_id: str | None
    market_id: str
    token_id: str | None
    intended_outcome: str | None
    action: str
    intended_price: float | None
    intended_size: float | None
    notional: float | None
    guard_result: str
    execution_policy_result: str
    status: str
    raw_intent_json: dict[str, object] = field(default_factory=dict)
    raw_guard_json: dict[str, object] = field(default_factory=dict)
    raw_policy_json: dict[str, object] = field(default_factory=dict)
