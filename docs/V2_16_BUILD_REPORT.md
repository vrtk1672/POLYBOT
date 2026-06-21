# V2.16 Build Report - Exit Cortex V2

## Short Summary

V2.16 Exit Cortex V2 is implemented and verified. It adds DB-backed exit plans, internal paper/shadow exit intents, trigger evaluation, exit quality, exit failures, orphan order detection, `/exits/*` APIs, dashboard truth, tests, and docs.

No live exits, live orders, external sends, order intents, generic orders, or external balance mutation were added.

## Files Created

- `app/exit_cortex/__init__.py`
- `app/exit_cortex/contracts.py`
- `app/exit_cortex/exit_errors.py`
- `app/exit_cortex/exit_plan_builder.py`
- `app/exit_cortex/exit_trigger_evaluator.py`
- `app/exit_cortex/exit_intent_builder.py`
- `app/exit_cortex/exit_event_manager.py`
- `app/exit_cortex/exit_quality.py`
- `app/exit_cortex/exit_failure_handler.py`
- `app/exit_cortex/position_monitor.py`
- `app/exit_cortex/liquidity_exit_checker.py`
- `app/exit_cortex/emergency_exit_evaluator.py`
- `app/exit_cortex/momentum_decay_evaluator.py`
- `app/exit_cortex/spread_exit_evaluator.py`
- `app/exit_cortex/news_invalidation_evaluator.py`
- `app/exit_cortex/service.py`
- `app/repositories/exit_plan_repository.py`
- `app/repositories/exit_intent_repository.py`
- `app/repositories/exit_event_repository.py`
- `app/repositories/exit_quality_repository.py`
- `app/repositories/exit_failure_repository.py`
- `app/api/exit_routes.py`
- `app/db/migrations/0054_v2_16_exit_cortex_v2.sql`
- `tests/test_v2_16_*.py`
- `docs/V2_16_EXIT_CORTEX_V2.md`
- `docs/V2_16_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/events/types.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## DB Migration

Command:

`powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`

Result:

`Applied migrations: 0054_v2_16_exit_cortex_v2.sql`

Tables:

- `exit_plans`
- `exit_intents`
- `exit_events`
- `exit_quality`
- `exit_failures`

## API Routes

- `GET /exits/health`
- `GET /exits/plans/recent`
- `GET /exits/plans/{exit_plan_id}`
- `GET /exits/intents/recent`
- `GET /exits/events/recent`
- `GET /exits/failures/recent`
- `GET /exits/quality/recent`
- `GET /exits/orphans`
- `POST /exits/plan`
- `POST /exits/evaluate`
- `POST /exits/emergency`

## Dashboard Changes

`OperatorDashboardQueryService` now includes real DB-backed `exits` overview fields:

- `exit_status`
- `active_exit_plans`
- `exit_intents_today`
- `triggers_today`
- `failures_today`
- `orphan_orders_count`
- `avg_exit_quality`
- `recent_exit_plans`
- `recent_exit_intents`
- `recent_exit_failures`
- `common_exit_reasons`
- `live_certified=false`

## Events Published

- `exit.plan.created`
- `exit.plan.blocked`
- `exit.plan.updated`
- `exit.trigger.detected`
- `exit.take_profit.triggered`
- `exit.partial_take_profit.triggered`
- `exit.stop_loss.triggered`
- `exit.max_hold.triggered`
- `exit.news_invalidated.triggered`
- `exit.spread_exit.triggered`
- `exit.momentum_decay.triggered`
- `exit.emergency.triggered`
- `exit.intent.created`
- `exit.intent.blocked`
- `exit.quality.recorded`
- `exit.failure.recorded`
- `exit.live.blocked`

## Tests Added

- `tests/test_v2_16_exit_plan_builder.py`
- `tests/test_v2_16_exit_trigger_evaluator.py`
- `tests/test_v2_16_exit_intent_builder.py`
- `tests/test_v2_16_exit_event_manager.py`
- `tests/test_v2_16_exit_quality.py`
- `tests/test_v2_16_exit_failure_handler.py`
- `tests/test_v2_16_position_monitor.py`
- `tests/test_v2_16_liquidity_exit_checker.py`
- `tests/test_v2_16_emergency_exit_evaluator.py`
- `tests/test_v2_16_momentum_decay_evaluator.py`
- `tests/test_v2_16_spread_exit_evaluator.py`
- `tests/test_v2_16_news_invalidation_evaluator.py`
- `tests/test_v2_16_exit_service.py`
- `tests/test_v2_16_exit_api.py`
- `tests/test_v2_16_exit_safety_guards.py`

## Tests Run And Exact Results

Targeted no-DB:

- `$files = (Get-ChildItem tests\test_v2_16_*.py).FullName; python -m uv run pytest $files -q`
- Result: `23 passed, 1 skipped in 49.67s`

DB-backed targeted:

- `$env:POLYBOT_DATABASE_URL='postgresql://polybot:polybot@127.0.0.1:55432/polybot'; $env:PHASE1_PERSISTENCE_ENABLED='true'; $files = (Get-ChildItem tests\test_v2_16_*.py).FullName; python -m uv run pytest $files -q`
- Result: `24 passed in 45.76s`

Regressions:

- V2.15 DB-backed: `20 passed in 84.52s`
- V2.15 standard: `19 passed, 1 skipped in 58.26s`
- V2.14 standard: `17 passed, 4 skipped in 14.86s`
- V2.13 standard: `12 passed, 4 skipped in 29.02s`
- V2.12 standard: `12 passed, 7 skipped in 20.31s`
- Runtime standard: `8 passed, 19 skipped in 20.76s`

Full suite:

- `python -m uv run pytest -q`
- Result: `337 passed, 395 skipped in 71.25s`

Notes:

- Direct DB-backed V2.14/runtime parallel attempts hit command timeouts after hanging worker processes; after cleanup, the standard V2.14/runtime regression suites passed cleanly.
- PowerShell wildcard expansion required `Get-ChildItem` file expansion.

## Runtime Verification Results

Docker/Postgres:

- `docker ps`: Postgres `polybot_phase1_pg` running, `0.0.0.0:55432->5432/tcp`; Grafana also running.
- `docker compose ps`: not applicable in repo root, no default compose file present.
- TCP check: `127.0.0.1:55432` reachable.
- Psycopg DB check: connected to database `polybot` as user `polybot`.

Runtime:

- Canonical script attempted: `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`
- Result: Windows Application Control blocked `uv run polybot` with `os error 4551`.
- Fallback used: direct Python startup, `python -m uv run python -c "from app.main import run; run()"`.
- Runtime started on `127.0.0.1:8000`.
- Runtime state: `DATA_ONLY`.
- Permissions: `can_create_live_orders=false`, `can_open_new_positions=false`, `can_close_positions=false`, `can_run_live_engine=false`.
- `/exits/health`: `HEALTHY`, `live_certified=false`.

Verified endpoints:

- `/healthz` OK
- `/runtime/state` OK
- `/runtime/health` OK
- `/events/lag` OK
- `/data/coverage` OK
- `/execution/health` OK
- `/exits/health` OK
- `/exits/plans/recent` OK
- `/exits/intents/recent` OK
- `/exits/events/recent` OK
- `/exits/failures/recent` OK
- `/exits/quality/recent` OK
- `/exits/orphans` OK

## Manual Smoke Results

Market used: `2169995` with explicit safe smoke payloads.

- `POST /exits/plan` dry_run=true: `written=false`; confirmed no row for `exit_plan_dryrun_v216`.
- `POST /exits/plan` dry_run=false: created exit plan.
- `POST /exits/evaluate` dry_run=true with take profit trigger: `written=false`.
- `POST /exits/evaluate` dry_run=false with take profit trigger: created internal `PAPER_SIM_EXIT` intent and quality row.
- Stop loss trigger: created internal exit intent.
- Max hold trigger: created internal exit intent.
- News invalidation trigger: created internal exit intent.
- Spread exit trigger: created internal exit intent.
- Bad liquidity: created `exit_failures` row and no intent.
- `POST /exits/emergency` dry_run=false: created internal emergency exit intent only.
- `GET /exits/orphans`: returned 4 internal V2 execution orders missing exit plans.

Runtime notes:

- Runtime remained `DATA_ONLY`; smoke passed explicit safe `runtime_mode='PAPER'` in manual evaluation payload for internal paper exit-intent creation.
- No external send occurred.
- `live_certified=false`.

## DB Row Verification

Before manual smoke:

- `exit_plans=0`
- `exit_intents=0`
- `exit_events=0`
- `exit_quality=0`
- `exit_failures=0`
- `orders_v2=5`
- `paper_orders=3`
- `live_orders=3`

After manual smoke:

- `exit_plans=7`
- `exit_intents=7`
- `exit_events=29`
- `exit_quality=7`
- `exit_failures=1`
- `orders_v2=5`
- `paper_orders=3`
- `live_orders=3`
- `order_intents=ABSENT`
- `orders=ABSENT`
- Dry-run row check: `exit_plan_dryrun_v216=0`
- Take-profit intent check: `exit_plan_smoke_tp_v216` intents = `1`
- Bad-liquidity failure check: `exit_plan_smoke_badliq_v216` failures = `1`

## Safety Checklist

- No entry without exit plan: YES
- Open internal orders/positions monitored: YES
- Orphan orders detected: YES
- DATA_ONLY dry-run/evaluation only: YES
- PAPER allows PAPER_SIM_EXIT only: YES
- SHADOW_LIVE allows SHADOW_EXIT_PLAN only: YES
- SMALL_LIVE/ATTACK_MODE live exits blocked until certification: YES
- live disabled by default: YES
- live_certified=false: YES
- Risk Gate respected: YES
- Risk Governor respected: YES
- Take profit triggers: YES
- Stop loss triggers: YES
- Max hold triggers: YES
- News invalidation triggers: YES
- Spread exit triggers: YES
- Emergency exit triggers: YES
- Missing exit liquidity records failure: YES
- Exit Cortex cannot create live orders: YES
- Exit Cortex cannot send live exits: YES
- Exit Cortex cannot mutate external balances: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Real closed-loop exit execution remains future work. V2.16 creates internal exit intents only.
- Existing `orders_v2` rows from V2.15 can be orphaned until an exit plan is attached; V2.16 reports them through `/exits/orphans`.
- Live exits remain uncertified and blocked.

## Phase Status

GREEN.

## Can Move To V2.17 No-Trade Intelligence

YES.
