# POLYBOT Paper Exit Loop + PnL Ledger Build Report

## Purpose

Package 4C-U/V implements safe paper position exit handling and paper PnL accounting. It gives POLYBOT a close ledger and daily PnL truth without creating trades or enabling execution.

## Current Reality Found

Runtime DB before implementation showed:

- `paper_intents=0`
- `paper_orders=0`
- `paper_positions=0`
- open paper positions `0`
- closed paper positions `0`
- `orders_v2=1` historical unchanged row
- `fills_v2=1` historical unchanged row
- `positions=0`
- `live_orders=0`
- `paper_fills` table absent

No open paper positions existed to close in real runtime.

## Files Created

- `app/db/migrations/0089_paper_exit_loop_pnl_ledger.sql`
- `app/services/paper_exit_loop.py`
- `tests/test_paper_exit_loop.py`
- `tests/test_paper_pnl_ledger.py`
- `tests/test_dashboard_paper_exit_pnl_truth.py`
- `tests/test_paper_exit_safety.py`
- `docs/POLYBOT_PAPER_EXIT_LOOP_PNL_LEDGER.md`
- `docs/POLYBOT_PAPER_EXIT_LOOP_PNL_LEDGER_BUILD_REPORT.md`

## Files Changed

- `app/api/routes.py`
- `app/ingestion/market_service.py`

## DB Migration

Applied migration:

- `0089_paper_exit_loop_pnl_ledger.sql`

Tables:

- `paper_position_closes`
- `paper_trade_ledger`
- `paper_daily_pnl`
- `paper_exit_loop_runs`

Constraints include one close per position and one close ledger row per position.

## Runtime Integration Point

`MarketService.refresh()` now runs `PaperExitLoopService.run_exit_loop()` after the existing paper runtime stage. The service respects SYSTEM power and the State Governor.

## API / Dashboard Changes

Added:

- `POST /paper/exits/run`
- `GET /dashboard/api/v2/paper-exits`
- `GET /dashboard/api/v2/paper-pnl`

Dashboard truth includes `mock_data=false`, open positions, closed trades, PnL, latest run, orphan count, stale price count, and zero artifact-creation deltas.

## Tests Added

- Take profit close.
- Stop loss close.
- Max hold close.
- Hold when no exit condition is met.
- Block close when exit price is missing.
- Realized and unrealized PnL calculations.
- Daily PnL update.
- Close ledger row.
- Duplicate close prevention.
- Orphan position checks.
- SYSTEM OFF block.
- No fake PnL with no paper positions.
- Dashboard truth.
- No real/live orders or fills.

## Tests Run

- `docker compose --profile test run --rm test python -m pytest tests/test_paper_exit_loop.py tests/test_paper_pnl_ledger.py tests/test_dashboard_paper_exit_pnl_truth.py tests/test_paper_exit_safety.py -q`
  - Result: `12 passed, 1 warning`

- `docker compose --profile test run --rm test python -m pytest tests/test_system_power.py tests/test_system_power_api.py tests/test_system_power_scheduler.py tests/test_dashboard_system_power_truth.py tests/test_brain_mesh_activation_service.py tests/test_brain_mesh_activation_scheduler.py tests/test_dashboard_brain_mesh_activation_truth.py tests/test_evidence_refresh_service.py tests/test_evidence_refresh_scheduler.py tests/test_dashboard_evidence_refresh_truth.py tests/test_downstream_evidence_recompute_service.py tests/test_downstream_evidence_recompute_scheduler.py tests/test_dashboard_downstream_recompute_truth.py tests/test_runtime_modes.py tests/test_state_governor.py -q`
  - Result: `40 passed, 1 warning`

- `docker compose --profile test run --rm test python -m pytest tests/test_v2_risk_core_service.py tests/test_v2_exit_foundation_service.py tests/test_v2_paper_eligibility_service.py tests/test_v2_paper_intent_service.py tests/test_v2_no_trade_ledger_service.py tests/test_phase2_execution_aware_paper.py -q`
  - Result: `31 passed`

## Runtime Smoke

Migration applied to runtime. API was rebuilt/restarted.

Smoke:

- `GET /healthz`: OK.
- `POST /system/power/off`: OFF, runtime work blocked.
- Waited one scheduler interval: no exit loop runs, closes, ledgers, orders, fills, or positions changed.
- `POST /system/power/on`: ON, runtime work allowed, paper/live/shadow still not allowed.
- `POST /paper/exits/run`: `NO_OPEN_PAPER_POSITIONS`.
- `GET /dashboard/api/v2/paper-exits`: `mock_data=false`, `open_paper_positions=0`, `closed_paper_trades=0`.
- `GET /dashboard/api/v2/paper-pnl`: `mock_data=false`, `open_paper_positions=0`, `closed_paper_trades=0`.

After smoke:

- `paper_intents=0`
- `paper_orders=0`
- `paper_positions=0`
- open paper positions `0`
- closed paper positions `0`
- `paper_position_closes=0`
- `paper_trade_ledger=0`
- `paper_daily_pnl=1` zero-valued derived daily truth row
- `paper_exit_loop_runs=3`
- `orders_v2=1` historical unchanged row
- `fills_v2=1` historical unchanged row
- `positions=0`
- `live_orders=0`

## PnL Examples From Tests

- Take profit: entry `0.50`, exit `0.60`, quantity `10` => realized PnL `+1.00`.
- Stop loss: entry `0.50`, exit `0.40`, quantity `10` => realized PnL `-1.00`.
- Mark only: entry `0.50`, mark `0.51`, quantity `10` => unrealized PnL `+0.10`.

## Orphan Position Checks

Fixture tests assert no closed position lacks a close row and no close ledger references a missing position. Runtime smoke reported `orphan_positions_count=0`.

## Safety Confirmation

- Live trading not enabled.
- Shadow not enabled.
- Paper execution not enabled.
- No paper positions fabricated.
- No fake closed trades.
- No fake realized PnL.
- No duplicate closes.
- No real/live orders created.
- `orders_v2` and `fills_v2` historical rows remained unchanged.
- `positions=0`.

## Remaining Risks

Runtime had no open paper positions, so real runtime could not demonstrate an actual close. The close/PnL path is proven through isolated test fixtures and will activate once a future safe Paper Execution + Position Ledger phase creates real open paper positions.

## Next Recommended Step

Proceed to the safe Paper Execution + Position Ledger phase only after review. That phase must create open paper positions through the already gated Paper Intent path before this exit loop can close real runtime paper positions.

## Phase Status

YELLOW: feature implemented and tested, runtime smoke safe and truthful, but no real open paper positions existed to close.
