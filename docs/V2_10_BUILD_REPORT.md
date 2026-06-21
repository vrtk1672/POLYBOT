# V2.10 Build Report - Context Brain + Capital Brain

## Summary

V2.10 adds separate Context Brain and Capital Brain analysis layers. Context Brain evaluates whether market probability may have changed. Capital Brain evaluates whether capital could be reserved under balance, budget, exposure, and memory constraints.

The implementation preserves the separation between interesting, worth money, allowed, and executable. It does not implement Opportunity Cortex, Strategy Router, Risk Governor, Execution Cortex, Exit Cortex, or live trading.

## Files Created

- `app/brains/__init__.py`
- `app/brains/contracts.py`
- `app/brains/brain_errors.py`
- `app/brains/context_brain.py`
- `app/brains/capital_brain.py`
- `app/brains/context_input_builder.py`
- `app/brains/capital_input_builder.py`
- `app/brains/context_signal_scorer.py`
- `app/brains/capital_recommendation_builder.py`
- `app/brains/service.py`
- `app/repositories/context_brain_run_repository.py`
- `app/repositories/context_brain_output_repository.py`
- `app/repositories/capital_brain_run_repository.py`
- `app/repositories/capital_brain_output_repository.py`
- `app/api/brain_routes.py`
- `app/db/migrations/0048_v2_10_context_capital_brains.sql`
- `tests/test_v2_10_context_brain.py`
- `tests/test_v2_10_capital_brain.py`
- `tests/test_v2_10_context_input_builder.py`
- `tests/test_v2_10_capital_input_builder.py`
- `tests/test_v2_10_brain_service.py`
- `tests/test_v2_10_brain_api.py`
- `tests/test_v2_10_brain_safety_guards.py`
- `docs/V2_10_CONTEXT_CAPITAL_BRAINS.md`
- `docs/V2_10_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/api/routes.py`
- `app/events/types.py`
- `app/brains/capital_input_builder.py`
- `app/services/query/operator_dashboard_query_service.py`
- `docs/POLYBOT_CONTEXT_INDEX.md`

Verification update:

- `app/brains/capital_input_builder.py` was corrected after DB-backed verification exposed a real bug: explicit empty manual capital input `{}` was being treated as absent input and falling back to paper capital state. It now remains explicit missing data and produces `insufficient_data`.

## Migration Added

- `app/db/migrations/0048_v2_10_context_capital_brains.sql`

## API Routes Added

- `GET /brains/health`
- `GET /brains/context/market/{market_id}`
- `GET /brains/capital/market/{market_id}`
- `GET /brains/market/{market_id}`
- `GET /brains/context/recent`
- `GET /brains/capital/recent`
- `GET /brains/blocked/recent`
- `POST /brains/context/analyze`
- `POST /brains/capital/analyze`
- `POST /brains/analyze`

## Dashboard Changes

Added DB-backed `brains` overview:

- context/capital run counts
- latest context shift
- latest capital allowed/block
- insufficient-data count
- capital-block count
- top shifts and blocks
- average context/allocation confidence
- common risks and capital block reasons

No fake data is emitted.

## Events Published

- `context_brain.run.started`
- `context_brain.output.created`
- `context_brain.insufficient_data`
- `capital_brain.run.started`
- `capital_brain.output.created`
- `capital_brain.blocked`
- `capital_brain.insufficient_data`
- `brain.snapshot.created`

## Tests Added

- Context Brain unit coverage
- Capital Brain unit coverage
- Input builder tests
- Service persistence/event tests
- API tests
- Safety guard tests

## Tests Run

Targeted V2.10 without DB:

`$files = (Get-ChildItem tests\test_v2_10_*.py).FullName; python -m uv run pytest $files -q`

Result: `15 passed, 7 skipped in 11.77s`.

V2.9 regression without DB:

`$files = (Get-ChildItem tests\test_v2_9_*.py).FullName; python -m uv run pytest $files -q`

Result: `17 passed, 7 skipped in 6.17s`.

V2.8 regression without DB:

`$files = (Get-ChildItem tests\test_v2_8_*.py).FullName; python -m uv run pytest $files -q`

Result: `11 passed, 5 skipped in 4.27s`.

Runtime/stage4 regression without DB:

`python -m uv run pytest tests\test_runtime_modes.py tests\test_mode_manager.py tests\test_runtime_api.py tests\test_stage4.py tests\test_stage4_env_isolation.py tests\test_env_runtime.py -q`

Result: `59 passed, 7 skipped in 10.53s`.

Full suite without DB:

`python -m uv run pytest -q`

Result: `244 passed, 371 skipped in 32.91s`.

DB-backed V2.10 attempt:

`$env:POLYBOT_DATABASE_URL="postgresql://polybot:polybot@127.0.0.1:55432/polybot"; ...`

Result: blocked by environment. `Test-NetConnection 127.0.0.1 -Port 55432` failed, Docker Desktop service was stopped, and `Start-Service com.docker.service` was denied.

DB-backed verification after Docker Desktop was available:

Docker/Postgres:

- `docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"`: `polybot_phase1_pg` up on `0.0.0.0:55432->5432/tcp`; `polybot_grafana` up on `3001->3000`.
- TCP check: `127.0.0.1:55432` reachable.
- DB check: connected to database `polybot` as user `polybot`.
- `docker compose ps`: repository root does not expose a compose project for the running phase DB; direct container check was used.

Migration:

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`
- First run applied `0048_v2_10_context_capital_brains.sql`.
- Follow-up run reported `No pending migrations.`
- Verified tables: `context_brain_runs`, `context_brain_outputs`, `capital_brain_runs`, `capital_brain_outputs`.
- Verified `schema_migrations` contains `0048_v2_10_context_capital_brains.sql`.

DB-backed V2.10 targeted tests:

- `python -m uv run pytest tests\test_v2_10_context_brain.py tests\test_v2_10_capital_brain.py tests\test_v2_10_context_input_builder.py tests\test_v2_10_capital_input_builder.py -q`
  - Result: `15 passed in 6.53s`.
- `python -m uv run pytest tests\test_v2_10_brain_service.py -q`
  - Initial result: one failure exposed explicit empty manual capital input falling back to paper capital state.
  - Fix applied in `app/brains/capital_input_builder.py`.
  - Rerun result: `3 passed in 326.42s`.
- `python -m uv run pytest tests\test_v2_10_brain_api.py -q`
  - Result: `1 passed in 123.69s`.
- `python -m uv run pytest tests\test_v2_10_brain_safety_guards.py -q`
  - Result: `3 passed in 288.57s`.

DB-backed V2.10 total: `22 passed`.

DB-backed regressions:

- V2.9 split regression total: `24 passed`.
  - `tests\test_v2_9_market_memory_service.py`: `3 passed in 294.61s`.
  - `tests\test_v2_9_market_memory_api.py tests\test_v2_9_market_memory_safety_guards.py`: `4 passed in 374.04s`.
  - V2.9 unit builder files: `17 passed in 4.45s`.
- V2.8 split regression total: `16 passed`.
  - `tests\test_v2_8_market_neuron_service.py`: `2 passed in 152.13s`.
  - `tests\test_v2_8_market_neuron_api.py`: `1 passed in 101.01s`.
  - `tests\test_v2_8_market_neuron_safety_guards.py`: `2 passed in 142.74s`.
  - V2.8 unit analyzer/builder files: `11 passed in 3.77s`.
- Runtime/safety regressions:
  - `python -m uv run pytest tests/test_runtime_modes.py -q`: `8 passed in 0.52s`.
  - `python -m uv run pytest tests/test_mode_manager.py -q`: `10 passed in 0.70s`.
  - `python -m uv run pytest tests/test_runtime_api.py -q`: `6 passed in 1058.65s`.

Note: DB-backed tests are slow because each isolated DB test schema runs migrations. Broad wildcard batches timed out under the command timeout, so verification was completed with expanded split file lists.

## Runtime Verification

Runtime verification completed with Postgres available.

Canonical script result:

- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1` loaded the expected safe environment but the local Windows Application Control policy blocked `uv` from spawning the `polybot` console entrypoint: `Failed to spawn: polybot ... Application Control policy has blocked this file`.

Equivalent direct runtime smoke:

- Started runtime with `.venv\Scripts\python.exe -c "from app.main import run; run()"` using the same runtime environment:
  - `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`
  - `PHASE1_PERSISTENCE_ENABLED=true`
  - `PHASE1_AUTO_MIGRATE=false`
  - `POLYBOT_RUNTIME_MODE=paper_safe`
  - `POLYBOT_EXECUTION_BACKEND=paper`
  - `LIVE_TRADING_ENABLED=false`
  - `LIVE_KILL_SWITCH=true`
  - `POLYBOT_API_HOST=127.0.0.1`
  - `POLYBOT_API_PORT=8000`
- Runtime startup log:
  - `startup_complete host=127.0.0.1 port=8000`
  - `v2_runtime_startup status=OK current_mode=DATA_ONLY`
  - `live_enabled=False`
  - `live_kill_switch=True`

Endpoint verification:

- `GET /healthz`: OK, `ready=true`.
- `GET /runtime/state`: OK, `current_mode=DATA_ONLY`; live/order permissions false.
- `GET /runtime/health`: OK, `overall_status=HEALTHY`, `current_mode=DATA_ONLY`.
- `GET /events/lag`: OK.
- `GET /data/coverage`: OK.
- `GET /market-neuron/health`: OK.
- `GET /market-memory/health`: OK.
- `GET /brains/health`: OK.
- `GET /brains/context/recent`: OK.
- `GET /brains/capital/recent`: OK.
- `GET /brains/blocked/recent`: OK.

Manual smoke with market `2169995`:

- `POST /brains/context/analyze` with `dry_run=true`: OK, `written=false`; no DB rows written.
- `POST /brains/context/analyze` with `dry_run=false`: OK, context row written; output had `context_shift=true`, `direction=YES`, `confidence=0.7006`.
- `POST /brains/capital/analyze` with `dry_run=true` and explicitly labeled smoke/test capital input: OK, `written=false`; no DB rows written.
- `POST /brains/capital/analyze` with `dry_run=false` and explicitly labeled smoke/test capital input: OK, capital row written; output had `capital_allowed=true`, `max_position_size_usd=90`, `engine_budget_remaining_usd=10`.
- `POST /brains/analyze` with `dry_run=false`: OK, both outputs written and combined snapshot returned.

DB row verification:

- Before smoke: all four V2.10 brain tables had `0` rows.
- After dry-runs: all four V2.10 brain tables still had `0` rows.
- After write smoke:
  - `context_brain_runs`: `2`
  - `context_brain_outputs`: `2`
  - `capital_brain_runs`: `2`
  - `capital_brain_outputs`: `2`
- Event Bus rows in `event_log`:
  - `context_brain.run.started`: `2`
  - `context_brain.output.created`: `2`
  - `capital_brain.run.started`: `2`
  - `capital_brain.output.created`: `2`
  - `brain.snapshot.created`: `1`

Safety smoke:

- Baseline trading table counts before smoke:
  - `paper_orders`: `3`
  - `paper_positions`: `3`
  - `live_orders`: `3`
  - `orders`: table absent
  - `order_intents`: table absent
  - `exit_intents`: table absent
- Counts after smoke were unchanged.
- Runtime state remained `DATA_ONLY`.
- `/runtime/state` reported:
  - `can_create_live_orders=false`
  - `can_open_new_positions=false`
  - `can_close_positions=false`
  - `can_open_paper_positions=false`
- Capital low-reserve dry-run: `capital_allowed=false`, `block_reason=cash_reserve_too_low`.
- Capital exhausted-engine-budget dry-run: `capital_allowed=false`, `block_reason=engine_budget_exhausted`.
- Missing capital dry-run: `insufficient_data=true`, reasons included `missing_available_capital` and `missing_balance`.
- Missing context dry-run: `insufficient_data=true`, reasons included `missing_market_memory` and `missing_context_signals`.
- AI/rules-risk dry-run: risks included `high_wording_risk` and `ai_cannot_override_risk`.

## What Is Fully Implemented

- Context Brain contracts and deterministic scorer
- Capital Brain contracts and deterministic recommendation builder
- Input builders
- Persistence repositories
- Service orchestration
- API routes
- Dashboard truth integration
- Event type registration and descriptions
- Safety tests for non-DB paths
- DB-backed migration, repository, service, API, and runtime verification

## What Is Partial

- Capital Brain uses existing paper capital snapshot or explicit safe test payloads; richer capital state remains future work.
- The canonical `scripts\start_runtime.ps1` path is blocked on this workstation by Windows Application Control when it invokes `uv run polybot`; direct Python runtime startup verified the same app and environment successfully.

## Safety Checklist

- KILL blocks trading: YES
- DATA_ONLY blocks orders: YES
- PAPER blocks live: YES
- SHADOW_LIVE blocks live: YES
- live disabled by default: YES
- Context Brain cannot create orders: YES
- Capital Brain cannot create orders: YES
- Context Brain cannot create order intents: YES
- Capital Brain cannot create order intents: YES
- No exits created: YES
- Capital Brain cannot mutate balances: YES
- AI context cannot override risk: YES
- Missing context data becomes insufficient_data: YES
- Missing capital data becomes insufficient_data: YES
- Context can say no real shift: YES
- Capital blocks if cash reserve too low: YES
- Capital respects engine budgets: YES
- Clear separation between interesting and worth money: YES
- Dashboard uses real data only: YES
- No secrets printed: YES
- State Governor respected: YES

## Remaining Risks

- Sparse capital data should continue to produce insufficient-data outputs until richer state exists.
- DB-backed regression tests are migration-heavy and slow on this workstation; split runs were required to avoid command timeout.
- The local Windows Application Control policy should be addressed separately so the canonical `uv run polybot` console entrypoint can start without using the direct Python equivalent.

## Recommendation

Phase status: GREEN.

Can move to V2.11 Opportunity Cortex: YES.
