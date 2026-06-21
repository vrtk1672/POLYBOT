from __future__ import annotations

from decimal import Decimal

from app.utils.json_safety import json_safe


def test_position_payload_with_decimal_mark_and_pnl_is_json_safe() -> None:
    payload = {
        "market_id": "691547",
        "side": "YES",
        "avg_entry": Decimal("0.39"),
        "mark_price": Decimal("0.35"),
        "unrealized": Decimal("-0.40"),
        "exit_status": "MAX_HOLD_TIME",
    }

    assert json_safe(payload) == {
        "market_id": "691547",
        "side": "YES",
        "avg_entry": 0.39,
        "mark_price": 0.35,
        "unrealized": -0.4,
        "exit_status": "MAX_HOLD_TIME",
    }
