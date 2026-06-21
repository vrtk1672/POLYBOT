# POLYBOT Paper Execution Idempotency Fix Build Report

## Current Reality Found

The active soak process PID `14268` was not running when checked. SYSTEM was set OFF with reason `stop soak due paper execution lineage consistency investigation`.

Runtime DB after stopping:

- `paper_intents=3`
- `paper_orders=6`
- `paper_fills=3`
- `paper_positions=6`
- `open_paper_positions=3`
- `closed_paper_positions=3`
- `paper_position_closes=3`
- `paper_trade_ledger=6`
- `paper_daily_pnl=2`
- `live_orders=0`
- `orders_v2=1`
- `fills_v2=1`
- canonical `positions=0`

## Exact Root Cause

The three new paper orders and three new open paper positions were created by the legacy runtime paper path:

- `RuntimePaperTradingService.process_cycle()`
- `ExecutionAwarePaperService.record_cycle()`

Those rows have no `source_intent_id`, no `paper_fill_id`, no `paper_fills` row, and no paper trade ledger OPEN row. The canonical safe paper execution path was not responsible for those three rows.

## Lineage Audit Findings

Safe paper rows:

- 3 safe orders from 3 paper intents
- 3 safe fills from those orders
- 3 safe positions from those fills
- all 3 safe positions closed
- all 3 safe positions have close rows and OPEN/CLOSE ledger rows

Legacy inconsistent rows:

- 3 orders have no `source_intent_id`
- 3 open positions have no `paper_fill_id`
- 3 open positions have no OPEN ledger row
- `paper_trade_ledger` stayed at 6 while `paper_positions` rose to 6

## Files Created

- `app/db/migrations/0096_paper_execution_lineage_lifecycle.sql`
- `tests/test_paper_lineage_consistency.py`
- `tests/test_soak_runner_paper_consistency_guards.py`
- `docs/POLYBOT_PAPER_EXECUTION_IDEMPOTENCY_FIX.md`
- `docs/POLYBOT_PAPER_EXECUTION_IDEMPOTENCY_FIX_BUILD_REPORT.md`

## Files Changed

- `app/ingestion/market_service.py`
- `app/services/paper_execution.py`
- `app/services/paper_exit_loop.py`
- `app/services/paper_dashboard_truth.py`
- `scripts/run_4h_technical_paper_soak.py`
- `tests/test_paper_execution_service.py`
- `tests/test_paper_exit_loop.py`
- `tests/test_paper_pnl_ledger.py`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_READINESS.md`
- `docs/POLYBOT_4H_TECHNICAL_PAPER_SOAK_REPORT_20260530T233959Z.md`

## DB Migration

Applied:

- `0096_paper_execution_lineage_lifecycle.sql`

Changes:

- expands `paper_intents.intent_status` lifecycle values
- adds `executed_at`
- adds `consumed_at`
- adds `closed_at`
- adds `execution_block_reason`

No destructive DB commands were run. No paper history was deleted.

## Tests Run

Focused regression:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_paper_execution_service.py tests/test_paper_lineage_consistency.py tests/test_paper_dashboard_truth.py tests/test_soak_runner_paper_consistency_guards.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py tests/test_paper_pnl_reconciliation.py -q
```

Result:

- `26 passed, 1 warning in 129.10s`

Broader targeted regression:

```powershell
docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_brain_dialogue_service.py tests/test_brain_dialogue_materialization.py tests/test_dashboard_brain_dialogue_api.py tests/test_neuron_dialogue_sources.py tests/test_neuron_dialogue_coverage_service.py tests/test_dashboard_neuron_dialogue_api.py tests/test_paper_execution_service.py tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_paper_lineage_consistency.py tests/test_paper_dashboard_truth.py tests/test_soak_runner_paper_consistency_guards.py tests/test_paper_no_live_safety.py tests/test_paper_no_orphans_duplicates.py tests/test_paper_pnl_reconciliation.py -q
```

Result:

- `54 passed, 1 warning in 255.81s`

## Runtime Smoke

SYSTEM was turned ON briefly and then OFF. No new scheduler cycle was observed after the API restart, so this is partial runtime smoke.

Before/mid/after counts:

- `paper_orders=6 -> 6 -> 6`
- `paper_fills=3 -> 3 -> 3`
- `paper_positions=6 -> 6 -> 6`
- `open_paper_positions=3 -> 3 -> 3`
- `paper_trade_ledger=6 -> 6 -> 6`
- `live_orders=0 -> 0 -> 0`
- `orders_v2=1 -> 1 -> 1`
- `fills_v2=1 -> 1 -> 1`
- canonical `positions=0 -> 0 -> 0`

Dashboard remained honest:

- `paper_lineage_consistency_status=RED`
- `positions_without_fills_count=3`
- `positions_without_open_ledger_count=3`
- readiness `RED`

## Safety Confirmation

- SYSTEM is OFF after validation.
- `live_orders=0`.
- `orders_v2` unchanged at 1.
- `fills_v2` unchanged at 1.
- canonical `positions` unchanged at 0.
- No live/shadow mode was enabled.
- No `.env` was modified.
- No inconsistent production rows were deleted.

## Remaining Risks

The interrupted soak left three legacy fill-less open paper positions in production DB. They are now visible as RED lineage truth, but not repaired.

## Next Recommended Step

Run ChatGPT review, then execute a scoped repair/quarantine phase for the three legacy paper positions before restarting any 4h soak.

## Phase Status

YELLOW.
