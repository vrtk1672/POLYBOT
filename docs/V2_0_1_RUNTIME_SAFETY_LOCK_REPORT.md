# V2.0.1 Runtime Safety Lock / Stage 4 Env Isolation Report

## Purpose

V2.0.1 closes the remaining V2.0 safety gap: Stage 4 tests were being contaminated by local `.env`, live credentials, and live kill-switch environment state. This is a narrow safety fix only. It does not implement V2.1, Event Bus, new trading logic, or Stage 4 redesign.

## Root Cause

`app/stage4/config.py` loaded `.env` at import time with `load_env_file_into_process()` and also configured `Stage4Settings` with `env_file=".env"`. That meant importing or constructing Stage 4 settings could silently pull local live credentials and live flags into tests.

The observed failures were:

- `tests/test_stage4.py::test_auth_validation_flags_missing_wallet_requirements`
- `tests/test_stage4.py::test_live_mode_submits_only_best_candidate_once`
- `tests/test_stage4.py::test_live_mode_falls_back_when_top_candidate_fails_minimum_size`

## Files Changed

- `app/stage4/config.py`
- `tests/conftest.py`
- `tests/test_stage4.py`
- `docs/V2_0_BUILD_REPORT.md`

## Files Created

- `tests/test_stage4_env_isolation.py`
- `docs/V2_0_1_RUNTIME_SAFETY_LOCK_REPORT.md`

## Before Behavior

- Importing Stage 4 config loaded local `.env`.
- Constructing `Stage4Settings()` could read `.env`.
- Local `LIVE_KILL_SWITCH`, `LIVE_TRADING_ENABLED`, and credential values could alter tests.
- Live-submission tests did not explicitly control kill-switch state.

## After Behavior

- `app/stage4/config.py` no longer loads `.env` at import time.
- `Stage4Settings` no longer has `env_file=".env"`.
- Stage 4 settings read current process env only, after test isolation or explicit runtime boundary loading.
- `LIVE_TRADING_ENABLED` defaults to `false`.
- `LIVE_KILL_SWITCH` defaults to `true`.
- Secret fields are marked `repr=False`.
- Stage 4 tests clear live-sensitive env vars automatically.
- Tests that intentionally exercise fake live submission explicitly set `LIVE_KILL_SWITCH=False`.

## Tests Added

- `tests/test_stage4_env_isolation.py`

Coverage includes:

- Stage 4 config import does not load local `.env`.
- Empty env has no live credentials.
- Safe defaults for live enabled and kill switch.
- Explicit fake env is respected.
- Local `.env` presence does not change Stage 4 settings.
- State Governor blocks `SEND_LIVE_ORDER` outside live-certified modes.
- PAPER, SHADOW_LIVE, and KILL block live even if env says live enabled.

## Tests Run

- `python -m uv run pytest tests/test_stage4.py -q`: 30 passed, 1 skipped.
- `python -m uv run pytest tests/test_stage4_env_isolation.py -q`: 10 passed.
- `python -m uv run pytest tests/test_env_runtime.py -q`: 1 passed.
- `python -m uv run pytest tests/test_runtime_modes.py -q`: 8 passed.
- `python -m uv run pytest tests/test_mode_manager.py -q`: 10 passed.
- `python -m uv run pytest tests/test_state_governor.py -q`: 7 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest tests/test_runtime_cycle_orchestrator.py -q`: 5 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest tests/test_runtime_api.py -q`: 6 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest tests/test_runtime_integration_guards.py -q`: 4 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest tests/test_phase2_execution_aware_paper.py -q`: 13 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest tests/test_phase9_dashboard_telegram.py -q`: 10 skipped because `POLYBOT_DATABASE_URL` was not present.
- `python -m uv run pytest`: 89 passed, 267 skipped.

## Runtime Verification

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: no pending migrations.
- `powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime.ps1`: runtime started successfully.
- `GET /runtime/state`: returned `DATA_ONLY`, kill false, live permissions false.
- `GET /runtime/health`: returned `HEALTHY`, current mode `DATA_ONLY`.
- `GET /runtime/mode`: returned `DATA_ONLY`, `can_create_live_orders=false`, `can_run_live_engine=false`.
- `POST /runtime/mode/request` to `PAPER`: succeeded and live permissions remained false.
- `POST /runtime/kill`: succeeded, set `KILL`, and trading permissions false.
- `POST /runtime/resume` to `DATA_ONLY`: succeeded and live permissions false.

## Safety Guarantees Verified

- Stage 4 import-time `.env` loading removed.
- Stage 4 tests isolate live-sensitive environment values.
- `LIVE_TRADING_ENABLED` defaults false.
- `LIVE_KILL_SWITCH` defaults true.
- Missing credentials mean auth invalid.
- State Governor blocks live send outside live-permitted modes.
- Env alone cannot enable live execution.
- No secrets were printed.
- Live remains disabled by default.

## Runtime / API / DB Impact

- DB migrations: none.
- API changes: none.
- Dashboard changes: none.
- Trading behavior: no new trading logic added.
- Runtime script behavior: preserved; explicit runtime boundary env loading remains in `app/config.py` and `scripts/start_runtime.ps1`.

## Remaining Risks

- Existing DB-backed tests still skip unless `POLYBOT_DATABASE_URL` is exported for the test process.
- Stage 4 still contains legacy live-cage logic; this phase only isolates environment loading and tests.

## Recommendation

Can move to V2.1 Event Bus / Neural Mesh Foundation: YES, after accepting the DB-backed skip behavior or running those tests with an explicit local test DB env.
