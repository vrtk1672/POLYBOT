from __future__ import annotations

from app.execution_v2.cancel_condition_evaluator import CancelConditionEvaluator


def test_cancel_condition_spread_widens_and_fill_rate_work():
    triggered, reasons = CancelConditionEvaluator().evaluate(cancel_if={"spread_widens": 100, "fill_rate_too_low": 0.5}, current={"spread_bps": 200, "fill_rate": 0.2})
    assert triggered
    assert "spread_widens" in reasons
    assert "fill_rate_too_low" in reasons


def test_ttl_expired_cancels_order():
    triggered, reasons = CancelConditionEvaluator().evaluate(cancel_if={"ttl_expired": True}, current={"ttl_expired": True})
    assert triggered
    assert reasons == ["ttl_expired"]

