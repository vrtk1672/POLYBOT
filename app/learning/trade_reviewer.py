from __future__ import annotations

from datetime import datetime
from typing import Any

from app.learning.contracts import TradeReview


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


class TradeReviewer:
    def review(self, payload: dict[str, Any]) -> TradeReview:
        market_id = str(payload.get("market_id") or "").strip()
        if not market_id:
            return TradeReview(
                market_id="UNKNOWN",
                review_status="INSUFFICIENT_DATA",
                insufficient_data=True,
                insufficient_data_reasons=["market_id_missing"],
                engine_result="UNKNOWN",
                evidence=payload,
                explanation="Trade review could not run because market_id is missing.",
            )

        entry_price = _float(payload.get("entry_price"))
        exit_price = _float(payload.get("exit_price"))
        size_usd = _float(payload.get("size_usd") or payload.get("notional_usd"))
        entry_time = _parse_dt(payload.get("entry_time"))
        exit_time = _parse_dt(payload.get("exit_time"))
        reasons: list[str] = []
        if entry_price is None:
            reasons.append("entry_price_missing")
        if exit_price is None:
            reasons.append("exit_price_missing")
        if size_usd is None:
            reasons.append("size_usd_missing")
        if payload.get("completed") is False:
            reasons.append("trade_not_completed")
        if reasons:
            return TradeReview(
                trade_id=payload.get("trade_id"),
                order_id=payload.get("order_id"),
                exit_plan_id=payload.get("exit_plan_id"),
                exit_intent_id=payload.get("exit_intent_id"),
                market_id=market_id,
                market_family=payload.get("market_family"),
                side=payload.get("side"),
                engine=payload.get("engine"),
                strategy_route_id=payload.get("strategy_route_id"),
                capital_allocation_id=payload.get("capital_allocation_id"),
                risk_gate_run_id=payload.get("risk_gate_run_id"),
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=entry_time,
                exit_time=exit_time,
                review_status="PENDING" if "trade_not_completed" in reasons else "INSUFFICIENT_DATA",
                insufficient_data=True,
                insufficient_data_reasons=reasons,
                engine_result="UNKNOWN",
                evidence=payload,
                explanation="Learning skipped outcome scoring until completed trade evidence exists.",
            )

        side = str(payload.get("side") or "YES").upper()
        signed_move = exit_price - entry_price
        if side in {"NO", "SHORT"}:
            signed_move *= -1
        realized_roi = signed_move / entry_price if entry_price else None
        realized_pnl = (realized_roi or 0.0) * size_usd
        hold_seconds = None
        roi_per_hour = None
        if entry_time and exit_time:
            hold_seconds = max(0, int((exit_time - entry_time).total_seconds()))
            if hold_seconds > 0 and realized_roi is not None:
                roi_per_hour = realized_roi / (hold_seconds / 3600)
        engine_result = "WIN" if realized_pnl > 0 else "LOSS" if realized_pnl < 0 else "BREAKEVEN"
        predicted_slippage = _float(payload.get("predicted_slippage_bps"))
        actual_slippage = _float(payload.get("actual_slippage_bps"))
        slippage_accuracy = None
        if predicted_slippage is not None and actual_slippage is not None:
            slippage_accuracy = max(0.0, 1.0 - abs(actual_slippage - predicted_slippage) / max(abs(predicted_slippage), 1.0))

        return TradeReview(
            trade_id=payload.get("trade_id"),
            order_id=payload.get("order_id"),
            exit_plan_id=payload.get("exit_plan_id"),
            exit_intent_id=payload.get("exit_intent_id"),
            market_id=market_id,
            market_family=payload.get("market_family"),
            side=side,
            engine=payload.get("engine"),
            strategy_route_id=payload.get("strategy_route_id"),
            opportunity_run_id=payload.get("opportunity_run_id"),
            capital_allocation_id=payload.get("capital_allocation_id"),
            risk_gate_run_id=payload.get("risk_gate_run_id"),
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            exit_time=exit_time,
            hold_seconds=hold_seconds,
            realized_pnl_usd=round(realized_pnl, 8),
            realized_roi=round(realized_roi or 0.0, 8),
            roi_per_hour=round(roi_per_hour, 8) if roi_per_hour is not None else None,
            max_favorable_excursion=_float(payload.get("max_favorable_excursion")),
            max_adverse_excursion=_float(payload.get("max_adverse_excursion")),
            entry_quality_score=_float(payload.get("entry_quality_score")),
            exit_quality_score=_float(payload.get("exit_quality_score")),
            slippage_accuracy_score=round(slippage_accuracy, 8) if slippage_accuracy is not None else None,
            signal_accuracy_score=_float(payload.get("signal_accuracy_score")),
            engine_result=engine_result,
            review_status="REVIEWED",
            insufficient_data=False,
            evidence=payload,
            explanation=f"Completed internal trade reviewed as {engine_result}.",
        )
