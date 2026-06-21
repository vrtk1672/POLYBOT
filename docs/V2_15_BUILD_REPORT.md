# V2.15 Build Report - Execution Cortex V2

## Summary

V2.15 implements internal paper/shadow execution infrastructure: order contracts, prechecks, PAPER_SIM simulation, SHADOW_PLAN planning, fill simulation, partial/failed fill handling, cancel condition evaluation, quality metrics, persistence, API routes, dashboard truth, tests, and docs.

No live order sender, order intent creation, exit creation, external request, or external balance mutation was added.

## Files Created

- `app/execution_v2/__init__.py`
- `app/execution_v2/contracts.py`
- `app/execution_v2/execution_errors.py`
- `app/execution_v2/order_contract_builder.py`
- `app/execution_v2/paper_execution_simulator.py`
- `app/execution_v2/shadow_execution_planner.py`
- `app/execution_v2/order_lifecycle_manager.py`
- `app/execution_v2/fill_simulator.py`
- `app/execution_v2/partial_fill_handler.py`
- `app/execution_v2/failed_fill_handler.py`
- `app/execution_v2/cancel_condition_evaluator.py`
- `app/execution_v2/slippage_curve.py`
- `app/execution_v2/execution_quality.py`
- `app/execution_v2/execution_latency.py`
- `app/execution_v2/service.py`
- `app/repositories/order_v2_repository.py`
- `app/repositories/order_event_v2_repository.py`
- `app/repositories/fill_v2_repository.py`
- `app/repositories/execution_error_repository.py`
- `app/repositories/execution_latency_repository.py`
- `app/repositories/execution_quality_repository.py`
- `app/api/execution_v2_routes.py`
- `app/db/migrations/0053_v2_15_execution_cortex_v2.sql`
- `tests/test_v2_15_order_contract_builder.py`
- `tests/test_v2_15_paper_execution_simulator.py`
- `tests/test_v2_15_shadow_execution_planner.py`
- `tests/test_v2_15_order_lifecycle_manager.py`
- `tests/test_v2_15_fill_simulator.py`
- `tests/test_v2_15_partial_fill_handler.py`
- `tests/test_v2_15_failed_fill_handler.py`
- `tests/test_v2_15_cancel_condition_evaluator.py`
- `tests/test_v2_15_slippage_curve.py`
- `tests/test_v2_15_execution_quality.py`
- `tests/test_v2_15_execution_service.py`
- `tests/test_v2_15_execution_api.py`
- `tests/test_v2_15_execution_safety_guards.py`
- `tests/test_v2_15_fixtures.py`
- `docs/V2_15_EXECUTION_CORTEX_V2.md`
- `docs/V2_15_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

- `app/db/migrations/0053_v2_15_execution_cortex_v2.sql`

Tables:

- `orders_v2`
- `order_events_v2`
- `fills_v2`
- `execution_errors`
- `execution_latency`
- `execution_quality`

Migration results:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- First DB-backed run: `Applied migrations: - 0053_v2_15_execution_cortex_v2.sql`
- Final rerun: `No pending migrations.`

## API Routes

- `GET /execution/health`
- `GET /execution/orders/recent`
- `GET /execution/orders/{order_id}`
- `GET /execution/fills/recent`
- `GET /execution/errors/recent`
- `GET /execution/quality/recent`
- `POST /execution/precheck`
- `POST /execution/paper/simulate`
- `POST /execution/shadow/plan`
- `POST /execution/cancel-evaluate`

## Dashboard Changes

Added DB-backed `execution` overview with live certification status, order counts, fill counts, cancelled counts, slippage, quality, recent orders, recent fills, recent errors, and recent quality records.

## Events Published

- `execution.order.created`
- `execution.order.blocked`
- `execution.order.submitted_paper`
- `execution.order.planned_shadow`
- `execution.order.partially_filled`
- `execution.order.filled`
- `execution.order.failed`
- `execution.order.cancelled`
- `execution.cancel_condition.triggered`
- `execution.fill.created`
- `execution.quality.recorded`
- `execution.error.recorded`
- `execution.live.blocked`

## Tests Added

V2.15 unit, service, API, and safety tests were added under `tests/test_v2_15_*.py`.

## Tests Run

Targeted V2.15 no-DB:

- `$files = (Get-ChildItem tests\test_v2_15_*.py).FullName; python -m uv run pytest $files -q`
- Final result after serializer cleanup: `19 passed, 1 skipped in 43.21s`

Targeted V2.15 DB-backed:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $files = (Get-ChildItem tests\test_v2_15_*.py).FullName; python -m uv run pytest $files -q`
- Result: `20 passed in 44.28s`

Relevant regressions:

- `python -m uv run pytest tests/test_v2_14_*.py -q` -> `17 passed, 4 skipped in 22.20s`
- `python -m uv run pytest tests/test_v2_13_*.py -q` -> `12 passed, 4 skipped in 36.11s`
- `python -m uv run pytest tests/test_v2_12_*.py -q` -> `12 passed, 7 skipped in 24.52s`
- `python -m uv run pytest tests/test_v2_11_*.py -q` -> `10 passed, 7 skipped in 11.28s`
- `python -m uv run pytest tests/test_v2_10_*.py -q` -> `15 passed, 7 skipped in 23.85s`
- `python -m uv run pytest tests/test_runtime_*.py -q` -> `8 passed, 19 skipped in 24.44s`

Full suite:

- `python -m uv run pytest -q`
- Result: `314 passed, 394 skipped in 61.58s (0:01:01)`

## Runtime Verification

Runtime startup:

- Canonical `scripts/start_runtime.ps1` / `uv run polybot` remains blocked by Windows Application Control in this environment.
- Runtime was started with the previously verified direct Python method:
  - `python -m uv run python -c "from app.main import run; run()"`

Runtime env included:

- `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
- `PHASE1_PERSISTENCE_ENABLED=true`
- `PHASE1_AUTO_MIGRATE=false`
- `POLYBOT_RUNTIME_MODE=paper_safe`
- `POLYBOT_EXECUTION_BACKEND=paper`
- `LIVE_TRADING_ENABLED=false`
- `LIVE_KILL_SWITCH=true`

Runtime remained safe:

- startup reported `current_mode=DATA_ONLY`
- `live_enabled=False`
- `live_certified=false`

Endpoint verification:

- `/healthz` -> OK
- `/runtime/state` -> OK
- `/runtime/health` -> OK
- `/events/lag` -> OK
- `/data/coverage` -> OK
- `/risk/health` -> OK, `HEALTHY`
- `/execution/health` -> OK, `HEALTHY`
- `/execution/orders/recent` -> OK, `count=4`
- `/execution/fills/recent` -> OK, `count=3`
- `/execution/errors/recent` -> OK, `count=1`
- `/execution/quality/recent` -> OK, `count=3`

## Manual Smoke

Manual smoke used market `2169995` variants with explicit safe payloads and placeholder `exit_plan_id`.

Results:

- `POST /execution/precheck` missing risk approval -> `allowed=false`, reason `missing_risk_approval`.
- `POST /execution/precheck` missing exit plan -> `allowed=false`, reason `missing_exit_plan`.
- `POST /execution/precheck` excessive slippage -> `allowed=false`, reason `slippage_too_high`.
- `POST /execution/paper/simulate` with `dry_run=true` -> `written=false`; order count unchanged.
- `POST /execution/paper/simulate` with `dry_run=false` and explicit PAPER smoke payload -> internal `PAPER_SIM` order and fill persisted only.
- `POST /execution/shadow/plan` with `dry_run=true` -> `written=false`; order count unchanged.
- `POST /execution/shadow/plan` with `dry_run=false` -> internal `SHADOW_PLAN` persisted with `not_sent_reason=shadow_plan_only_no_external_send`.
- `POST /execution/cancel-evaluate` with `spread_widens` -> internal order cancelled.
- `POST /execution/paper/simulate` with low depth -> internal `PARTIALLY_FILLED` paper order.
- `POST /execution/paper/simulate` without exit plan -> `execution_errors` row persisted with `missing_exit_plan`.

## DB Row Verification

Final DB row counts after smoke:

- `orders_v2=4`
- `order_events_v2=9`
- `fills_v2=3`
- `execution_quality=3`
- `execution_errors=1`
- `execution_latency=3`
- `paper_orders=3` unchanged from baseline
- `paper_positions=3` unchanged from baseline
- `live_orders=3` unchanged from baseline
- `orders=ABSENT`
- `order_intents=ABSENT`
- `exit_intents=ABSENT`

Observed V2.15 rows:

- filled internal `PAPER_SIM`
- cancelled internal `PAPER_SIM`
- planned internal `SHADOW_PLAN`
- partially filled internal `PAPER_SIM`
- blocked execution error for missing exit plan

## Safety Checklist

- KILL blocks execution: YES
- DATA_ONLY blocks persisted executable order: YES
- PAPER allows PAPER_SIM only: YES
- SHADOW_LIVE allows SHADOW_PLAN only: YES
- SMALL_LIVE/ATTACK_MODE live send blocked until certification: YES
- live disabled by default: YES
- live_certified=false: YES
- Risk Gate approval required: YES
- Risk Governor OK required: YES
- Strategy route required: YES
- Capital allocation required: YES
- Exit plan required: YES
- No risk snapshot blocks order: YES
- No exit plan blocks order: YES
- Slippage too high blocks order: YES
- Missing bid/ask/depth blocks order: YES
- Paper execution matches orderbook assumptions: YES
- Partial fill handled: YES
- Failed fill handled: YES
- Cancel condition works: YES
- Shadow execution sends nothing: YES
- Execution cannot create live orders: YES
- Execution cannot create order intents: YES
- Execution cannot create exits: YES
- Execution cannot mutate external balances: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Real orderbook/liquidity availability remains dependent on V2.8 data coverage; manual smoke used explicit safe payloads.
- V2.16 must provide real exit plans; V2.15 only requires and stores an `exit_plan_id` reference.
- Runtime background refresh can temporarily slow endpoint smoke during large Gamma scans.
- Canonical PowerShell runtime startup remains affected by Windows Application Control, so direct Python startup was used and documented.

## Phase Status

V2.15 status: GREEN.

## Recommendation

Can move to V2.16 Exit Cortex V2: YES.
