from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from app.utils.json_safety import json_dumps, json_safe
from app.neural_bus.contracts import NeuralEvent


def test_decimal_nested_payload_serializes_safely() -> None:
    payload = {
        "pnl": Decimal("-0.400000"),
        "nested": [{"price": Decimal("0.39"), "when": datetime(2026, 6, 18, tzinfo=UTC)}],
        "day": date(2026, 6, 18),
        "id": uuid4(),
        "codes": {"A", "B"},
    }

    safe = json_safe(payload)
    encoded = json.dumps(safe, sort_keys=True)

    assert '"pnl": -0.4' in encoded
    assert "2026-06-18T00:00:00+00:00" in encoded


def test_runtime_metadata_decimal_payload_uses_safe_dumps() -> None:
    encoded = json_dumps({"paper_flow": {"paper_pnl": {"daily": Decimal("42.377267")}}}, sort_keys=True)

    assert encoded == '{"paper_flow": {"paper_pnl": {"daily": 42.377267}}}'


def test_neural_event_accepts_uuid_and_decimal_payloads() -> None:
    uid = uuid4()
    event = NeuralEvent(
        event_type="PNL_CHANGED",
        source_component="test",
        source_type="paper_runtime",
        payload_json={"position_id": uid, "pnl": Decimal("-0.4")},
        metadata_json={"seen_at": datetime(2026, 6, 18, tzinfo=UTC)},
    )

    assert event.safe_payload()["position_id"] == str(uid)
    assert event.safe_payload()["pnl"] == -0.4
