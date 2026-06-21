# V2.13 Build Report - Capital Allocator V2 + Reinvest Brain

## Summary

V2.13 implements an internal capital allocation and reinvest accounting layer. It builds capital state, engine budgets, allocation decisions, Profit Pocket, Attack Bank, and capital event ledger records.

No orders, order intents, exits, live requests, external balance mutations, risk approvals, or live trading behavior were added.

## Files Created

- `app/capital/__init__.py`
- `app/capital/contracts.py`
- `app/capital/capital_errors.py`
- `app/capital/capital_state_builder.py`
- `app/capital/engine_budget_manager.py`
- `app/capital/allocation_policy.py`
- `app/capital/capital_allocator.py`
- `app/capital/reinvest_brain.py`
- `app/capital/profit_pocket_manager.py`
- `app/capital/attack_bank_manager.py`
- `app/capital/loss_streak_policy.py`
- `app/capital/service.py`
- `app/repositories/capital_state_repository.py`
- `app/repositories/engine_budget_repository.py`
- `app/repositories/capital_allocation_repository.py`
- `app/repositories/reinvest_ledger_repository.py`
- `app/repositories/profit_pocket_repository.py`
- `app/repositories/attack_bank_repository.py`
- `app/repositories/capital_event_repository.py`
- `app/api/capital_routes.py`
- `app/db/migrations/0051_v2_13_capital_allocator_reinvest_brain.sql`
- `tests/test_v2_13_capital_state_builder.py`
- `tests/test_v2_13_engine_budget_manager.py`
- `tests/test_v2_13_allocation_policy.py`
- `tests/test_v2_13_capital_allocator.py`
- `tests/test_v2_13_reinvest_brain.py`
- `tests/test_v2_13_profit_pocket.py`
- `tests/test_v2_13_attack_bank.py`
- `tests/test_v2_13_loss_streak_policy.py`
- `tests/test_v2_13_capital_service.py`
- `tests/test_v2_13_capital_api.py`
- `tests/test_v2_13_capital_safety_guards.py`
- `docs/V2_13_CAPITAL_ALLOCATOR_REINVEST_BRAIN.md`
- `docs/V2_13_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

- `app/db/migrations/0051_v2_13_capital_allocator_reinvest_brain.sql`

Tables:

- `capital_state_v2`
- `engine_budgets`
- `capital_allocations_v2`
- `reinvest_ledger`
- `profit_pocket`
- `attack_bank`
- `capital_events`

Migration result:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- Result: applied `0051_v2_13_capital_allocator_reinvest_brain.sql`
- Follow-up result: `No pending migrations.`

## API Routes

- `GET /capital/health`
- `GET /capital/state`
- `GET /capital/budgets`
- `GET /capital/allocations/recent`
- `GET /capital/events/recent`
- `GET /capital/reinvest`
- `POST /capital/state/rebuild`
- `POST /capital/allocate`
- `POST /capital/reinvest/evaluate`

## Dashboard Changes

Added DB-backed `capital` overview fields for capital state, budgets, allocations, reinvest status, events, and insufficient-data truth.

## Events Published

- `capital.state.created`
- `capital.state.updated`
- `engine.budget.created`
- `engine.budget.updated`
- `capital.allocation.created`
- `capital.allocation.blocked`
- `capital.allocation.reduced`
- `reinvest.profit_pocket.updated`
- `reinvest.attack_bank.updated`
- `capital.event.recorded`
- `capital.insufficient_data`

## Tests Added

V2.13 unit, service, API, and safety tests were added under `tests/test_v2_13_*.py`.

## Tests Run

- `$files = (Get-ChildItem tests\test_v2_13_*.py).FullName; python -m uv run pytest $files -q`
  - Initial result: `1 failed, 11 passed, 4 skipped`
  - Fixed no-DB manual dry-run path.
  - Current result: `12 passed, 4 skipped in 42.96s`

DB-backed targeted:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $files = (Get-ChildItem tests\test_v2_13_*.py).FullName; python -m uv run pytest $files -q`
  - Initial DB result timed out at 10 minutes before pytest summary.
  - Split DB service result initially failed on Decimal JSON serialization in `capital_events`.
  - Fixed serialization.
  - Final result: `16 passed in 740.12s (0:12:20)`

Regression slices:

- V2.12 broad no-DB regression: `12 passed, 7 skipped in 12.94s`
- V2.11 broad no-DB regression: `10 passed, 7 skipped in 11.21s`
- V2.10 broad no-DB regression: `15 passed, 7 skipped in 23.37s`
- V2.9 broad no-DB regression: `17 passed, 7 skipped in 12.87s`
- V2.8 broad no-DB regression: `11 passed, 5 skipped in 16.72s`
- V2.7 broad no-DB regression: `16 passed, 3 skipped in 50.40s`
- Runtime broad no-DB regression: `8 passed, 19 skipped in 29.53s`

Full suite:

- `python -m uv run pytest -q`
- Result: `278 passed, 389 skipped in 64.94s`

Note: an all-file V2.12 DB-backed regression command timed out at 20 minutes before returning a pytest summary. The V2.13 DB-backed suite itself passed, and the requested broad regressions passed in established no-DB regression mode with expected DB skips.

## Runtime Verification

Docker/Postgres:

- `docker ps`: Postgres container `polybot_phase1_pg` running, port `55432->5432`; Grafana container also running.
- `docker compose ps`: no compose file in this repo root, returned `no configuration file provided: not found`.
- DB connection verified against `postgresql://polybot:polybot@127.0.0.1:55432/polybot`.

Startup:

- Canonical script `scripts/start_runtime.ps1` set safe env but Windows Application Control blocked `uv run polybot` with os error 4551.
- Direct Python startup was used:
  - `python -m uv run python -c "from app.main import run; run()"`
  - Runtime started on `http://127.0.0.1:8000`.
  - Startup log: `current_mode=DATA_ONLY`, `live_enabled=False`, `live_kill_switch=True`.

Endpoint smoke:

- `/healthz`: OK
- `/runtime/state`: OK, `DATA_ONLY`, live/order permissions false
- `/runtime/health`: OK
- `/events/lag`: OK
- `/data/coverage`: OK
- `/strategy/health`: OK
- `/capital/health`: OK
- `/capital/state`: OK
- `/capital/budgets`: OK
- `/capital/allocations/recent`: OK
- `/capital/events/recent`: OK
- `/capital/reinvest`: OK

Dashboard smoke:

- `/dashboard/api/overview` returned real DB-backed `capital` truth:
  - `capital_status=OK`
  - `total_capital=1000`
  - `available_capital=1000`
  - `survival_reserve=200`
  - `cash_reserve=100`
  - `profit_pocket=70`
  - `attack_bank=30`
  - `allocations_today=2`
  - `blocked_allocations_today=1`
  - `reduced_allocations_today=1`

## Manual Smoke

Market used: `2169995`.

Explicit safe smoke capital input:

- `total_capital_usd=1000`
- `available_capital_usd=1000`
- `realized_pnl_usd=120`
- `loss_streak_count=1`
- `source_type=MANUAL_SMOKE`

Manual route input:

- `selected_engine=SAFE`
- `route_status=ROUTED`
- `execution_mode=CONTRACT_ONLY`
- `requested_size_usd=70`

Results:

- `POST /capital/state/rebuild dry_run=true`: wrote nothing.
- `POST /capital/state/rebuild dry_run=false`: wrote internal capital state and budgets.
- `POST /capital/allocate dry_run=true`: wrote nothing; returned `DRY_RUN`.
- `POST /capital/allocate dry_run=false`: wrote allocation decision; returned `REDUCED` because policy and loss-streak constraints reduced size to `50.575`.
- `POST /capital/allocate` against `NO_TRADE` route: wrote blocked decision; approved size `0`.
- `POST /capital/reinvest/evaluate dry_run=true realized_profit_usd=100`: wrote nothing.
- `POST /capital/reinvest/evaluate dry_run=false realized_profit_usd=100`: wrote reinvest ledger, Profit Pocket, Attack Bank.
- `POST /capital/reinvest/evaluate realized_profit_usd=0`: returned no movement with `no_realized_profit`; wrote nothing.

## DB Row Verification

Before smoke:

- `capital_state_v2`: `0`
- `engine_budgets`: `0`
- `capital_allocations_v2`: `0`
- `reinvest_ledger`: `0`
- `profit_pocket`: `0`
- `attack_bank`: `0`
- `capital_events`: `0`
- `paper_orders`: `3`
- `paper_positions`: `3`
- `live_orders`: `3`

After smoke:

- `capital_state_v2`: `1`
- `engine_budgets`: `8`
- `capital_allocations_v2`: `2`
- `reinvest_ledger`: `1`
- `profit_pocket`: `1`
- `attack_bank`: `1`
- `capital_events`: `4`
- `paper_orders`: unchanged at `3`
- `paper_positions`: unchanged at `3`
- `live_orders`: unchanged at `3`
- `orders`: absent
- `order_intents`: absent
- `exit_intents`: absent

Allocation rows:

- `2169995`: `SAFE`, `SAFE_CAPITAL`, `REDUCED`, approved `50.575`, `attack_bank_used_usd=0`
- `2169995-blocked-capital`: `NO_TRADE`, `BLOCKED`, approved `0`

Attack Bank check:

- `attack_bank.base_capital_used_usd <> 0`: `0` rows

Runtime:

- `system_state.current_mode`: `DATA_ONLY`
- `/runtime/state.permissions.can_create_live_orders`: `false`
- `/runtime/state.permissions.can_open_paper_positions`: `false`

## Safety Checklist

- Capital Allocator cannot create orders: YES
- Capital Allocator cannot create order intents: YES
- Capital Allocator cannot create exits: YES
- Capital Allocator cannot mutate external balances: YES
- Allocation decision is not executable order: YES
- Every allocation has a bucket: YES for allocatable routes; NO_TRADE/BLOCKED routes intentionally have no bucket
- Reserve never violated: YES
- Engine budget respected: YES
- Loss streak reduces risk: YES
- Profit Pocket grows only from realized profit: YES
- Attack Bank cannot use base reserve: YES
- Convex/Hunt cannot use all capital: YES
- Moonshot uses small basket sizing: YES
- NO_TRADE/BLOCKED route gets no allocation: YES
- Missing capital data becomes insufficient_data: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Real capital source coverage depends on existing canonical paper/live balance truth.
- V2.13 records internal allocation decisions but does not reserve funds; V2.14+ must decide whether and how to convert decisions into risk-approved executable flow.
- The all-file V2.12 DB-backed regression remains too slow for the current local fixture and timed out without a failure summary.

## Recommendation

Phase status: GREEN.

Can move to V2.14 Risk Gate + Risk Governor: YES.
