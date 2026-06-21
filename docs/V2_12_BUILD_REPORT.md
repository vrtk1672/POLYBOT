# V2.12 Build Report - Strategy Router + Engines

## Summary

V2.12 implements the Strategy Router and engine-contract layer. It evaluates SAFE, STRIKE, CONVEX, MAKER, HUNT, MOONSHOT_BASKET, REINVEST, and NO_TRADE against V2.11 opportunity truth and emits one selected strategy route with a full engine contract when appropriate.

No orders, order intents, exit intents, balance mutation, capital reservation, risk approval, execution, or live trading behavior was added.

## Files Created

- `app/strategy/__init__.py`
- `app/strategy/contracts.py`
- `app/strategy/strategy_errors.py`
- `app/strategy/router.py`
- `app/strategy/engine_contract_builder.py`
- `app/strategy/engine_rejection_builder.py`
- `app/strategy/engine_cooldown_manager.py`
- `app/strategy/engines/__init__.py`
- `app/strategy/engines/safe_engine.py`
- `app/strategy/engines/strike_engine.py`
- `app/strategy/engines/convex_engine.py`
- `app/strategy/engines/maker_engine.py`
- `app/strategy/engines/hunt_engine.py`
- `app/strategy/engines/moonshot_basket_engine.py`
- `app/strategy/engines/reinvest_engine.py`
- `app/strategy/engines/no_trade_engine.py`
- `app/strategy/service.py`
- `app/repositories/strategy_route_run_repository.py`
- `app/repositories/strategy_route_repository.py`
- `app/repositories/engine_decision_repository.py`
- `app/repositories/engine_rejection_repository.py`
- `app/repositories/engine_cooldown_repository.py`
- `app/api/strategy_routes.py`
- `app/db/migrations/0050_v2_12_strategy_router_engines.sql`
- `tests/test_v2_12_strategy_router.py`
- `tests/test_v2_12_engine_contract_builder.py`
- `tests/test_v2_12_safe_engine.py`
- `tests/test_v2_12_strike_engine.py`
- `tests/test_v2_12_convex_engine.py`
- `tests/test_v2_12_maker_engine.py`
- `tests/test_v2_12_hunt_engine.py`
- `tests/test_v2_12_moonshot_basket_engine.py`
- `tests/test_v2_12_reinvest_engine.py`
- `tests/test_v2_12_no_trade_engine.py`
- `tests/test_v2_12_strategy_service.py`
- `tests/test_v2_12_strategy_api.py`
- `tests/test_v2_12_strategy_safety_guards.py`
- `docs/V2_12_STRATEGY_ROUTER_ENGINES.md`
- `docs/V2_12_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

- `app/db/migrations/0050_v2_12_strategy_router_engines.sql`

Tables:

- `strategy_route_runs`
- `strategy_routes_v2`
- `engine_decisions`
- `engine_rejections`
- `engine_cooldowns`

Migration result:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- Result: applied `0050_v2_12_strategy_router_engines.sql`
- Verified `schema_migrations.version = '0050_v2_12_strategy_router_engines.sql'`

## API Routes

- `GET /strategy/health`
- `GET /strategy/market/{market_id}`
- `GET /strategy/recent`
- `GET /strategy/engines`
- `GET /strategy/rejections/recent`
- `GET /strategy/cooldowns`
- `GET /strategy/run/{run_id}`
- `POST /strategy/route`

## Dashboard Changes

Added DB-backed `strategy` overview:

- strategy_status
- runs_today
- routes_today
- no_trade_today
- blocked_today
- active_cooldowns
- latest_route_ts
- routes_by_engine
- rejections_by_engine
- top_route_reasons
- common_rejection_reasons
- recent_routes
- recent_no_trade_routes
- engine_confidence_average
- errors

Dashboard smoke returned real DB-backed strategy truth after manual routing.

## Events Published

- `strategy.route.run.started`
- `strategy.route.created`
- `strategy.route.no_trade`
- `strategy.engine.decision.created`
- `strategy.engine.rejected`
- `strategy.engine.cooldown.created`
- `strategy.route.insufficient_data`

## Tests Added

- Strategy router tests
- Engine contract builder tests
- SAFE / STRIKE / CONVEX / MAKER / HUNT / MOONSHOT_BASKET / REINVEST / NO_TRADE tests
- Strategy service tests
- Strategy API tests
- Strategy safety guard tests

## Tests Run

Targeted unit slice:

- `python -m uv run pytest tests/test_v2_12_strategy_router.py tests/test_v2_12_engine_contract_builder.py tests/test_v2_12_safe_engine.py tests/test_v2_12_strike_engine.py tests/test_v2_12_convex_engine.py tests/test_v2_12_maker_engine.py tests/test_v2_12_hunt_engine.py tests/test_v2_12_moonshot_basket_engine.py tests/test_v2_12_reinvest_engine.py tests/test_v2_12_no_trade_engine.py -q`
  - Result: `12 passed in 2.51s`

No-DB expanded V2.12 file list:

- `$files = (Get-ChildItem tests\test_v2_12_*.py).FullName; python -m uv run pytest $files -q`
  - Result: `12 passed, 7 skipped in 14.73s`

DB-backed V2.12:

- `python -m uv run pytest tests/test_v2_12_strategy_service.py -q`
  - Initial result: environment error before test code executed because `polybot_phase1_pg` had exited and PostgreSQL was in crash recovery.
  - After recovery: `3 passed in 428.60s`
- `python -m uv run pytest tests/test_v2_12_strategy_api.py -q`
  - Result: `1 passed in 145.87s`
- `python -m uv run pytest tests/test_v2_12_strategy_safety_guards.py -q`
  - Result: `3 passed in 493.60s`

V2.12 total: `19 passed`.

Regressions:

- V2.11 no-DB expanded file list: `10 passed, 7 skipped in 4.85s`
- V2.10 no-DB expanded file list: `15 passed, 7 skipped in 17.59s`
- V2.9 no-DB expanded file list: `17 passed, 7 skipped in 10.67s`
- V2.8 no-DB expanded file list: `11 passed, 5 skipped in 8.04s`
- V2.7 no-DB expanded file list: `16 passed, 3 skipped in 38.46s`
- V2.6 no-DB expanded file list: `9 passed, 11 skipped in 21.54s`
- V2.5 no-DB expanded file list: `18 passed, 6 skipped in 19.84s`
- V2.4 no-DB expanded file list: `18 passed, 8 skipped in 19.75s`
- Runtime no-DB expanded file list: `8 passed, 19 skipped in 23.85s`

Full suite:

- `python -m uv run pytest -q`
  - Result: `266 passed, 385 skipped in 58.00s`

## Runtime Verification

Docker/Postgres:

- `polybot_phase1_pg` had exited before DB verification and required `docker start polybot_phase1_pg`.
- PostgreSQL crash recovery completed and the DB became reachable at `127.0.0.1:55432`.
- Migration applied and verified.

Runtime:

- Direct Python runtime startup was used, matching V2.10/V2.11 because local Windows Application Control blocks the canonical `uv run polybot` console entrypoint.
- Environment:
  - `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
  - `PHASE1_PERSISTENCE_ENABLED=true`
  - `PHASE1_AUTO_MIGRATE=false`
  - `POLYBOT_RUNTIME_MODE=paper_safe`
  - `POLYBOT_EXECUTION_BACKEND=paper`
  - `LIVE_TRADING_ENABLED=false`
  - `LIVE_KILL_SWITCH=true`

Endpoint smoke:

- `/healthz`: OK
- `/runtime/state`: OK, `DATA_ONLY`, live/order permissions false
- `/runtime/health`: OK
- `/events/lag`: OK
- `/data/coverage`: OK
- `/market-neuron/health`: OK
- `/market-memory/health`: OK
- `/brains/health`: OK
- `/opportunities/health`: OK
- `/strategy/health`: OK, initially `EMPTY`
- `/strategy/recent`: OK
- `/strategy/engines`: OK
- `/strategy/rejections/recent`: OK
- `/strategy/cooldowns`: OK

## Manual Smoke

Market used: `2169995`.

- `POST /strategy/route` with `dry_run=true`: returned route and wrote no rows.
- `POST /strategy/route` with `dry_run=false`: persisted a `SAFE` route with `route_status=ROUTED` and a full `CONTRACT_ONLY` engine contract.
- Blocked payload: selected `NO_TRADE` with `route_status=BLOCKED`.
- HUNT-like payload without `hunt_approval`: selected `NO_TRADE`; HUNT rejection reason was `hunt_requires_governor_approval`.
- HUNT-like payload with `hunt_approval=true`: selected `HUNT` with `route_status=ROUTED`.
- Dashboard `/dashboard/api/overview` returned DB-backed `strategy` truth with `runs_today=4`, `routes_today=4`, `no_trade_today=1`, `blocked_today=1`, and `active_cooldowns=1`.

## DB Row Verification

Before smoke:

- `strategy_route_runs`: `0`
- `strategy_routes_v2`: `0`
- `engine_decisions`: `0`
- `engine_rejections`: `0`
- `engine_cooldowns`: `0`
- `paper_orders`: `3`
- `paper_positions`: `3`
- `live_orders`: `3`

After dry-run:

- all strategy counts stayed `0`
- trading/balance counts unchanged

After write smoke:

- `strategy_route_runs`: `4`
- `strategy_routes_v2`: `4`
- `engine_decisions`: `32`
- `engine_rejections`: `24`
- `engine_cooldowns`: `1`
- `paper_orders`: unchanged at `3`
- `paper_positions`: unchanged at `3`
- `live_orders`: unchanged at `3`
- `orders`: table absent
- `order_intents`: table absent
- `exit_intents`: table absent

Latest routes:

- `2169995`: `SAFE`, `ROUTED`
- `2169995-blocked-strategy`: `NO_TRADE`, `BLOCKED`
- `2169995-hunt-no`: `NO_TRADE`, `NO_TRADE`
- `2169995-hunt-yes`: `HUNT`, `ROUTED`

Events:

- `strategy.route.run.started`: `4`
- `strategy.route.created`: `4`
- `strategy.route.no_trade`: `2`
- `strategy.engine.decision.created`: `32`
- `strategy.engine.rejected`: `24`
- `strategy.engine.cooldown.created`: `1`

## What Is Fully Implemented

- Strategy contracts
- Strategy Router
- SAFE engine
- STRIKE engine
- CONVEX engine
- MAKER engine
- HUNT engine with approval boundary
- MOONSHOT_BASKET engine
- REINVEST metadata-only rejection
- NO_TRADE engine
- Engine contract builder
- Engine rejection builder
- Cooldown manager
- Repositories
- API routes
- Dashboard truth fields
- Migration
- Tests and runtime smoke

## What Is Partial

- Strategy thresholds are deterministic and conservative but not outcome-calibrated.
- REINVEST remains metadata-only until V2.13.
- HUNT approval remains an explicit input boundary until V2.14 Risk Governor exists.

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Strategy Router cannot create orders: YES
- Strategy Router cannot create order intents: YES
- Strategy Router cannot create exits: YES
- Strategy Router cannot mutate balances: YES
- Engine contracts are not executable orders: YES
- Every route has an engine: YES
- Every non-NO_TRADE route has a full contract: YES
- NO_TRADE is always valid: YES
- Hard opportunity blocks force NO_TRADE/BLOCKED: YES
- HUNT requires approval: YES
- Candidate engines are revalidated: YES
- Missing data becomes insufficient_data: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Engine thresholds are deterministic and documented but not yet outcome-calibrated.
- REINVEST is intentionally blocked until V2.13.
- HUNT approval is an explicit placeholder until V2.14 Risk Governor exists.

## Phase Status

GREEN.

Can move to V2.13 Capital Allocator V2 + Reinvest Brain: YES.

