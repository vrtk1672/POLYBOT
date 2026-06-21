# V2.3.1 Runtime Startup Responsiveness Fix

## Purpose

V2.3.1 fixes the runtime readiness issue that kept V2.3 in YELLOW. The goal was narrow: make canonical FastAPI startup responsive quickly without changing trading behavior, AI behavior, or future-phase scope.

## Root Cause

Two startup behaviors combined to make the process look alive while API requests timed out:

1. `app/main.py` awaited `market_service.refresh()` inside the FastAPI lifespan before yielding startup complete. Uvicorn could have a live Python process while the app was still not ready to serve requests.
2. Once the blocking startup refresh was removed, the scheduler still launched its first refresh immediately. That heavy refresh could monopolize the event loop during endpoint verification.

AI Brain was not contacting Ollama or cloud providers during startup. The issue was runtime refresh timing.

## Investigation Findings

- `scripts/start_runtime.ps1` correctly targets `127.0.0.1:8000`.
- V2.3 AI routes are lazy and do not call local/cloud models during app creation.
- `/ai/health` can return structured unavailable status without Ollama.
- Event Bus, Data Foundation, and AI route registration did not require external services.
- The blocking call was the startup refresh path in `app/main.py`, followed by immediate scheduler refresh.

## Files Changed

- `app/main.py`
- `app/scheduler.py`
- `tests/test_v2_3_1_runtime_startup_responsiveness.py`
- `docs/V2_3_1_RUNTIME_STARTUP_RESPONSIVENESS_FIX.md`
- `docs/V2_3_BUILD_REPORT.md`
- `docs/POLYBOT_CONTEXT_INDEX.md`

## Fix Implemented

- Removed the synchronous `await market_service.refresh()` from FastAPI lifespan startup.
- Added lightweight `GET /healthz`, which performs no DB/dashboard/AI/refresh work.
- Added `RefreshScheduler.initial_delay_seconds`.
- Configured canonical runtime startup to delay the first scheduled refresh by `settings.refresh_interval_seconds`, allowing the API to become responsive before heavy refresh work starts.
- Added regression tests proving app startup does not call market refresh, Ollama, or cloud AI.

## Startup Behavior Before

Startup performed heavy market refresh before FastAPI readiness. The process could remain alive without responding on port `8000`.

## Startup Behavior After

Startup initializes safe state, registers services/routes, starts scheduler with an initial delay, yields FastAPI readiness, and responds on `8000`. Heavy refresh happens after the initial delay.

## Tests Added

- `tests/test_v2_3_1_runtime_startup_responsiveness.py`

Covered:

- `/healthz` is lightweight.
- Startup does not run `MarketService.refresh`.
- AI routes register without Ollama/cloud calls.
- `/ai/health` works without Ollama.
- Startup does not call local AI generation or cloud escalation.

## Tests Run

- `python -m uv run pytest tests/test_v2_3_1_runtime_startup_responsiveness.py -q`: `4 passed`.
- `python -m uv run pytest tests/test_v2_3_ai_api.py -q`: `3 skipped` because DB env was absent.
- `python -m uv run pytest tests/test_v2_3_local_ai_worker.py -q`: `3 passed`.
- `python -m uv run pytest tests/test_v2_3_cloud_escalation.py -q`: `3 passed`.
- `python -m uv run pytest tests/test_runtime_api.py -q`: `6 skipped` because DB env was absent.
- `python -m uv run pytest tests/test_runtime_integration_guards.py -q`: `4 skipped` because DB env was absent.
- V2.3 regressions: passed or skipped as expected without DB env.
- Safety regressions: `tests/test_runtime_modes.py` `8 passed`, `tests/test_mode_manager.py` `10 passed`, `tests/test_stage4.py` `30 passed, 1 skipped`, `tests/test_stage4_env_isolation.py` `10 passed`, `tests/test_env_runtime.py` `1 passed`.
- V2.1/V2.2 key API tests skipped as expected without DB env.
- Full suite: `140 passed, 324 skipped`.

## Runtime Verification Results

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: `No pending migrations`.
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`: started canonical runtime.
- `GET /healthz`: returned `{"status":"ok","app":"polybot","ready":true}`.
- `GET /runtime/state`: returned `DATA_ONLY`, kill false, live permissions false.
- `GET /runtime/health`: returned `HEALTHY`.
- `GET /runtime/mode`: returned `DATA_ONLY` with live permissions false.
- `GET /events/lag`: returned event metrics with `failed_events=0`, `open_dlq_count=0`.
- `GET /data/coverage`: returned real DB coverage, including orderbook coverage `0.0`.
- `GET /ai/health`: returned `local_ai_available=false`, `cloud_enabled=false`.
- `GET /ai/costs`: returned zero-cost truth.
- `GET /ai/cache`: returned empty cache truth.
- `GET /ai/escalations`: returned empty escalation truth.
- `GET /ai/decisions`: returned empty decision truth.

## Safety Guarantees

- Live remains disabled by default.
- No orders or order intents were created by this fix.
- Startup does not call Ollama.
- Startup does not call cloud AI.
- AI remains interpretation-only.
- State Governor remains authoritative.
- Stage 4 env isolation remains green.
- Dashboard and API responses remain real truth, not mock data.
- No secrets were printed.

## Remaining Risks

The first scheduled market refresh can still be heavy once it begins. That is acceptable for V2.3.1 readiness, but a later runtime hardening phase should move long synchronous DB/API work out of the event loop or into a worker boundary.

## Status

V2.3.1: GREEN.

V2.3 final status: GREEN.
