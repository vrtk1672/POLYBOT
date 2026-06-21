from __future__ import annotations

from typing import Any

from app.no_trade.contracts import NoTradeDecision
from app.no_trade.no_trade_errors import NoTradeValidationError
from app.no_trade.reason_classifier import NoTradeReasonClassifier


class NoTradeCandidateTracker:
    def __init__(self, classifier: NoTradeReasonClassifier | None = None) -> None:
        self.classifier = classifier or NoTradeReasonClassifier()

    def build_decision(self, payload: dict[str, Any]) -> NoTradeDecision:
        source_layer = str(payload.get("source_layer") or "").lower()
        if not source_layer:
            raise NoTradeValidationError("source_layer is required")
        primary = payload.get("primary_reason")
        raw_reasons = payload.get("reasons") or ([primary] if primary else [])
        if not primary and raw_reasons:
            primary = raw_reasons[0]
        if not primary:
            raise NoTradeValidationError("primary_reason is required")
        reasons = [self.classifier.classify(str(item), source_layer=source_layer) for item in raw_reasons]
        if not reasons:
            raise NoTradeValidationError("at least one reason is required")
        primary_reason = self.classifier.classify(str(primary), source_layer=source_layer).reason
        insufficient = bool(payload.get("insufficient_data")) or any(reason.reason == "unknown_reason" for reason in reasons)
        insufficient_reasons = list(payload.get("insufficient_data_reasons") or [])
        if any(reason.reason == "unknown_reason" for reason in reasons):
            insufficient_reasons.append("unknown_reason")
        kwargs = {}
        if payload.get("no_trade_id"):
            kwargs["no_trade_id"] = payload.get("no_trade_id")
        return NoTradeDecision(
            **kwargs,
            market_id=str(payload.get("market_id") or ""),
            market_family=payload.get("market_family"),
            side=payload.get("side"),
            candidate_engine=payload.get("candidate_engine"),
            source_layer=source_layer,
            source_run_id=payload.get("source_run_id"),
            source_record_id=payload.get("source_record_id"),
            decision_status=payload.get("decision_status") or "NO_TRADE",
            primary_reason=primary_reason,
            reasons=reasons,
            risk_flags=payload.get("risk_flags") or [],
            opportunity_score=payload.get("opportunity_score"),
            strategy_route_status=payload.get("strategy_route_status"),
            capital_allocation_status=payload.get("capital_allocation_status"),
            risk_gate_decision=payload.get("risk_gate_decision"),
            execution_block_reason=payload.get("execution_block_reason"),
            exit_block_reason=payload.get("exit_block_reason"),
            would_have_entry_price=payload.get("would_have_entry_price"),
            would_have_size_usd=payload.get("would_have_size_usd"),
            would_have_max_loss_usd=payload.get("would_have_max_loss_usd"),
            decision_confidence=payload.get("decision_confidence", 0.7),
            data_confidence=payload.get("data_confidence", 0.7),
            insufficient_data=insufficient,
            insufficient_data_reasons=insufficient_reasons,
            explanation=payload.get("explanation") or f"No-trade decision recorded because {primary_reason}.",
        )
