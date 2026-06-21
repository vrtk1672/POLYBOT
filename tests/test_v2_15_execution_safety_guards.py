from __future__ import annotations

from pathlib import Path


def test_execution_v2_has_no_live_order_or_intent_writes():
    service_text = Path("app/execution_v2/service.py").read_text(encoding="utf-8")
    forbidden = ["INSERT INTO live_orders", "INSERT INTO order_intents", "INSERT INTO exit_intents", "send_order", "create_order_intent"]
    for needle in forbidden:
        assert needle not in service_text

