# POLYBOT Safe Paper Execution + Position Ledger Build Report

## Purpose

Implement the missing middle layer from Paper Intent to simulated paper order/fill/position, ready for the existing Paper Exit Loop + PnL Ledger.

## Current Reality Found

Runtime before implementation:

- `paper_intents=0`
- executable paper intents `0`
- blocked paper intents `0`
- `paper_orders=0`
- `paper_fills` absent before migration
- `paper_positions=0`
- open paper positions `0`
- closed paper positions `0`
- `paper_position_closes=0`
- `paper_trade_ledger=0`
- `paper_daily_pnl=1`
- `orders_v2=1` historical unchanged row
- `fills_v2=1` historical unchanged row
- `positions=0`
- `live_orders=0`
- runtime mode `DATA_ONLY`

No valid runtime paper intents existed.

## Files Created

- `app/db/migrations/0090_safe_paper_execution_position_ledger.sql`
- `app/services/paper_execution.py`
- `tests/test_paper_execution_service.py`
- `tests/test_paper_position_ledger.py`
- `tests/test_dashboard_paper_execution_truth.py`
- `tests/test_paper_execution_safety.py`
- `docs/POLYBOT_SAFE_PAPER_EXECUTION_POSITION_LEDGER.md`
- `docs/POLYBOT_SAFE_PAPER_EXECUTION_POSITION_LEDGER_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/ingestion/market_service.py`

## DB Migration

Applied migration:

- `0090_safe_paper_execution_position_ledger.sql`

New tables:

- `paper_fills`
- `paper_execution_runs`

Existing canonical tables reused:

- `paper_runs`
- `paper_signals`
- `paper_orders`
- `paper_positions`
- `paper_trade_ledger`

## API / Dashboard Changes

Added:

- `POST /paper/execution/run`
- `GET /dashboard/api/v2/paper-execution`

Dashboard fields include `mock_data=false`, `paper_intents_total`, `executable_intents`, `blocked_intents`, `paper_orders`, `paper_fills`, `paper_positions`, `open_paper_positions`, latest timestamps, block reasons, `real_orders=0`, `real_orders_total`, `live_orders=0`, and safety deltas.

## Runtime Integration Point

`MarketService.refresh()` now runs Paper Intent Gate, then Paper Execution, then Paper Exit Loop. Paper Execution respects SYSTEM power and State Governor. It does not alter runtime mode.

## Tests Added

- SYSTEM OFF blocks execution.
- DATA_ONLY permission blocks valid executable intent.
- No valid intents creates no paper artifacts.
- Valid intent creates paper order.
- Valid order creates simulated paper fill.
- Valid fill creates open paper position.
- Duplicate run skips duplicates.
- Missing market/side/quantity blocks.
- Missing/stale orderbook blocks.
- Limit not marketable blocks.
- Fill uses trusted orderbook price.
- Dashboard truth.
- No real/live artifacts.
- Paper Exit Loop sees opened paper position.

## Tests Run

- `docker compose --profile test run --rm test python -m pytest tests/test_paper_execution_service.py tests/test_paper_position_ledger.py tests/test_dashboard_paper_execution_truth.py tests/test_paper_execution_safety.py -q`
  - Result: `12 passed, 1 warning`

- `docker compose --profile test run --rm test python -m pytest tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_dashboard_paper_exit_pnl_truth.py tests/test_paper_exit_safety.py tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py tests/test_evidence_refresh_service.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py tests/test_downstream_evidence_recompute_service.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py tests/test_runtime_modes.py tests/test_state_governor.py -q`
  - Result: `52 passed, 1 warning`

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_service.py tests/test_v2_no_trade_ledger_service.py tests/test_phase2_execution_aware_paper.py -q`
  - Result: `31 passed`

Total final passing tests: `95`.

## Runtime Smoke

Runtime migration applied and API restarted.

Baseline after migration:

- `paper_intents=0`
- executable paper intents `0`
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- open paper positions `0`
- closed paper positions `0`
- `paper_position_closes=0`
- `paper_trade_ledger=0`
- `paper_daily_pnl=1`
- `paper_execution_runs=0`
- `orders_v2=1`
- `fills_v2=1`
- `positions=0`
- `live_orders=0`

SYSTEM OFF smoke:

- `POST /system/power/off`: OFF, runtime work blocked.
- Waited one scheduler interval.
- `paper_execution_runs=0`, paper orders/fills/positions unchanged, real/live unchanged.

SYSTEM ON smoke:

- `POST /system/power/on`: ON, runtime mode remained `DATA_ONLY`, paper allowed `false`, live allowed `false`.
- `POST /paper/execution/run`: `NO_VALID_PAPER_INTENTS`.
- Scheduler interval also created a `NO_VALID_PAPER_INTENTS` execution run.
- `GET /dashboard/api/v2/paper-execution`: `mock_data=false`, `paper_orders=0`, `paper_fills=0`, `paper_positions=0`, `open_paper_positions=0`, `real_orders=0`, `real_orders_total=1`, `live_orders=0`.

Final runtime counts:

- `paper_intents=0`
- executable paper intents `0`
- blocked paper intents `0`
- `paper_orders=0`
- `paper_fills=0`
- `paper_positions=0`
- open paper positions `0`
- closed paper positions `0`
- `paper_position_closes=0`
- `paper_trade_ledger=0`
- `paper_daily_pnl=1`
- `paper_execution_runs=3`
- `orders_v2=1` historical unchanged row
- `fills_v2=1` historical unchanged row
- `positions=0`
- `live_orders=0`

## Execution Examples From Tests

- Valid paper intent with quantity `10`, intended price `0.55`, fresh best ask `0.52` created one `FILLED` paper order, one paper fill at `0.52`, and one open paper position.
- Re-running the same intent created no duplicate order, fill, or position.
- Valid intent in DATA_ONLY with paper permission denied returned `PAPER_BLOCKED_BY_MODE` and created no artifacts.
- Missing or stale orderbook returned `NO_VALID_PAPER_INTENTS` and created no fill.

## Safety Confirmation

- SYSTEM OFF blocks Paper Execution.
- SYSTEM ON does not enable live.
- Runtime mode remains DATA_ONLY.
- No paper orders/fills/positions were fabricated in runtime.
- No real orders were created.
- No live orders were created.
- `orders_v2` and `fills_v2` historical rows remained unchanged.
- No canonical `positions` were created.
- Paper Exit Loop can see fixture-created open paper positions in tests.

## Remaining Risks

Runtime has no valid paper intents. The real runtime path cannot produce `paper_orders > 0` until upstream eligibility/risk/exit produces valid intents and the operator moves to a mode that permits paper execution. The full execution path is proven with controlled fixtures.

## Next Recommended Step

Proceed to Paper Dashboard + Regression + Soak Readiness after review. Do not move to live or shadow execution.

## Phase Status

GREEN by package rule: implementation complete, tests prove valid execution path, runtime honestly reports `NO_VALID_PAPER_INTENTS`, no fake runtime artifacts, no live/real execution.
