from __future__ import annotations

from app.ai_brain.cost_ledger import AICostLedger
from app.db.migrate import run_migrations


def test_local_and_cloud_costs_record_and_aggregate(postgres_test_schema) -> None:
    run_migrations()
    ledger = AICostLedger()
    ledger.record_cost(model_name="qwen3:8b", provider="local", task_type="MARKET_CLASSIFICATION", estimated_cost=0.0)
    ledger.record_cost(model_name="cloud", provider="cloud", task_type="TRAP_PRECHECK", estimated_cost=0.05)
    summary = ledger.summarize_costs()
    assert summary["total_estimated_cost"] == 0.05
    assert summary["cloud_calls_today"] == 1
    assert summary["local_calls_today"] == 1
    assert summary["cost_by_model"]
