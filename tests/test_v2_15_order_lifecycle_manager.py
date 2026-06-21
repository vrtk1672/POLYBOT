from __future__ import annotations

from app.execution_v2.order_lifecycle_manager import OrderLifecycleManager


def test_lifecycle_statuses():
    manager = OrderLifecycleManager()
    assert manager.created_status("PAPER_SIM") == "SUBMITTED_PAPER"
    assert manager.created_status("SHADOW_PLAN") == "PLANNED_SHADOW"
    assert manager.status_from_fill(filled_size=1, remaining_size=0) == "FILLED"

