# V2.0 Build Report

## Current Status

Implemented and verified. V2-specific tests pass. Full suite still has unrelated Stage 4 environment-sensitive failures caused by existing live credential and kill-switch state.

V2.0.1 Runtime Safety Lock completed: YES. Stage 4 config no longer loads `.env` at import time, Stage 4 tests isolate live-sensitive env values, and the full suite now reports 89 passed and 267 skipped in the no-DB-env test process.

## Files Created

- `app/runtime/__init__.py`
- `app/runtime/modes.py`
- `app/runtime/contracts.py`
- `app/runtime/state_governor.py`
- `app/runtime/mode_manager.py`
- `app/runtime/cycle_orchestrator.py`
- `app/runtime/service_registry.py`
- `app/runtime/health_truth.py`
- `app/runtime/safe_startup.py`
- `app/runtime/runtime_errors.py`
- `app/repositories/runtime_state_repository.py`
- `app/repositories/runtime_cycle_repository.py`
- `app/repositories/service_health_repository.py`
- `app/api/runtime_routes.py`
- `tests/test_runtime_modes.py`
- `tests/test_state_governor.py`
- `tests/test_mode_manager.py`
- `tests/test_runtime_cycle_orchestrator.py`
- `tests/test_runtime_api.py`
- `tests/test_runtime_integration_guards.py`
- `docs/V2_0_CORE_RUNTIME_FOUNDATION.md`
- `docs/V2_0_BUILD_REPORT.md`

## Files Changed

- `app/main.py`
- `app/scheduler.py`
- `app/ingestion/market_service.py`
- `app/services/runtime_paper_trading.py`
- `app/services/live_runtime.py`
- `app/services/operator_control.py`
- `app/services/telegram_bot.py`
- `app/services/query/operator_dashboard_query_service.py`
- `app/api/routes.py`

## Migration Added

- `app/db/migrations/0038_v2_runtime_foundation.sql`

## Tests Added

- `tests/test_runtime_modes.py`
- `tests/test_mode_manager.py`
- `tests/test_state_governor.py`
- `tests/test_runtime_cycle_orchestrator.py`
- `tests/test_runtime_api.py`
- `tests/test_runtime_integration_guards.py`

## Tests Run

- `python -m uv run pytest tests/test_runtime_modes.py -q`: 8 passed.
- `python -m uv run pytest tests/test_mode_manager.py -q`: 10 passed.
- `python -m uv run pytest tests/test_state_governor.py -q`: 7 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_cycle_orchestrator.py -q`: 5 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_api.py -q`: 6 skipped without DB env.
- `python -m uv run pytest tests/test_runtime_integration_guards.py -q`: 4 skipped without DB env.
- With `POLYBOT_DATABASE_URL=postgresql://polybot:polybot@127.0.0.1:55432/polybot`:
  - `tests/test_state_governor.py`: 7 passed.
  - `tests/test_runtime_cycle_orchestrator.py`: 5 passed.
  - `tests/test_runtime_api.py`: 6 passed.
  - `tests/test_runtime_integration_guards.py`: 4 passed.
- `python -m uv run pytest tests/test_stage4.py -q`: 3 failed, 27 passed, 1 skipped.
- `python -m uv run pytest tests/test_phase2_execution_aware_paper.py -q`: 13 skipped without DB env.
- `python -m uv run pytest tests/test_phase9_dashboard_telegram.py -q`: 10 skipped without DB env.
- `python -m uv run pytest`: 3 failed, 76 passed, 267 skipped.

## Unrelated Test Failures

- `tests/test_stage4.py::test_auth_validation_flags_missing_wallet_requirements`
  - Related to V2.0: No.
  - Likely cause: existing environment supplies wallet requirements despite `_env_file=None`.
  - Recommended fix: isolate Stage 4 credential tests from process environment.
- `tests/test_stage4.py::test_live_mode_submits_only_best_candidate_once`
  - Related to V2.0: No.
  - Likely cause: existing `LIVE_KILL_SWITCH` environment state remains enabled during the test.
  - Recommended fix: patch `LIVE_KILL_SWITCH=False` in the test settings or isolate stage4 env.
- `tests/test_stage4.py::test_live_mode_falls_back_when_top_candidate_fails_minimum_size`
  - Related to V2.0: No.
  - Likely cause: existing `LIVE_KILL_SWITCH` environment state remains enabled during the test.
  - Recommended fix: patch `LIVE_KILL_SWITCH=False` in the test settings or isolate stage4 env.

## Runtime Verification

- `powershell -ExecutionPolicy Bypass -File .\scripts\migrate_runtime.ps1`: applied `0038_v2_runtime_foundation.sql`.
- Runtime started via canonical `scripts/start_runtime.ps1`.
- `GET /runtime/state`: returned `DATA_ONLY`, kill false, paper/live permissions false.
- `GET /runtime/health`: returned `HEALTHY`, current mode `DATA_ONLY`, last successful V2 cycle persisted.
- `GET /runtime/mode`: returned `DATA_ONLY` with permissions summary.
- `POST /runtime/mode/request` to `PAPER`: succeeded.
- `POST /runtime/kill`: succeeded and set `KILL`.
- `POST /runtime/resume` to `DATA_ONLY`: succeeded.

## Fully Implemented

- System State Governor.
- Mode Manager.
- Runtime permissions contract.
- Runtime cycle ledger and stage guards.
- Service registry.
- Health truth endpoint.
- Safe startup initialization.
- Runtime API routes.
- Minimal dashboard runtime truth.
- Critical paper/live/scheduler integration guards.

## Partially Integrated

- Shadow-live is guarded by V2 permissions, but still depends on existing env/backend branching.
- Service heartbeat coverage is foundational; many services are registered but not yet actively heartbeating.
- Telegram `/kill`, `/resume`, and `/pause` are wired, while other commands remain read/query oriented.

## Remaining Legacy

- Stage 3 SQLite paper trading remains legacy and untouched.
- Stage 4 live cage remains an additional safety layer.
- `MarketService.refresh()` remains the central runtime cycle.

## Safety Guarantees Verified

- KILL blocks trading.
- DATA_ONLY blocks order and position creation.
- PAPER blocks live order sending.
- SHADOW_LIVE blocks live order sending.
- Actor and reason are required for mode changes.
- Allowed and blocked transitions persist to `system_state_history`.
- Runtime startup initializes `DATA_ONLY`.
- Live was not enabled.

## Unresolved Risks

- Stage 4 tests are environment-sensitive and currently fail when live credentials or kill-switch env values leak in.
- DB-backed tests are slow because each isolated schema replays the full migration chain.
- `HealthTruthService` currently treats registered but stopped noncritical services as acceptable unless stale/error.

## Next Step Recommendation

Build V2.1 Risk Governor: explicit SMALL_LIVE certification, notional caps, per-market caps, live dry-run attestations, and dashboard-visible operator approval workflow.
