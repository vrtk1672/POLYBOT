from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TradeClassificationContract:
    id: str
    trade_classification_run_id: str
    market_id: str
    cycle_id: str | None
    decision_id: str | None
    cognition_summary_id: str | None
    whale_market_score_id: str | None
    primary_trade_type: str
    secondary_trade_types_json: list[str] = field(default_factory=list)
    classification_confidence: float = 0.0
    risk_posture_class: str = "DO_NOT_DEPLOY"
    suggested_bucket_class: str | None = None
    classification_reason_codes_json: list[str] = field(default_factory=list)
    classification_reason_text: str = ""
    explanation_json: dict[str, object] = field(default_factory=dict)
    classifier_version: str = ""
