# Current Runtime Readiness Build Report

## Summary

Implemented Phase 2 Current Runtime Readiness as a read-only truth surface.

The new endpoint is:

- `GET /dashboard/api/v2/control/runtime-readiness`

It returns a Truth Contract envelope and also exposes the readiness fields at the top level for direct operator inspection.

## Runtime Truth Added

The readiness object includes:

- `runtime_life_state`
- `system_power_state`
- `governor_allows_collect_data`
- `scheduler_state`
- `scheduler_blocked_reason`
- `supervisor_state`
- `active_cycle_state`
- `last_successful_cycle_state`
- `full_monitor_run_state`
- `full_monitor_run_label = DIAGNOSTIC_ONLY`
- `runtime_supervisor_truth_scope = PROCESS_LOCAL`
- `full_monitor_truth_scope = PROCESS_LOCAL`
- `source_map`
- `blockers`, `warnings`, `errors`

## Sources

- `system_state.system_power`
- `StateGovernor.can_execute(COLLECT_DATA)` when runtime state already exists
- `service_health.scheduler`
- `runtime_cycles_v2`
- process-local Runtime Supervisor store
- process-local Full Monitor Run store

Full Monitor Run is explicitly diagnostic-only and never contributes to `ALIVE`.

## Changed Files

- `app/control_center/runtime_readiness.py`
- `app/api/routes.py`
- `app/control_center/query_service.py`
- `app/runtime/health_truth.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_runtime_readiness.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/CURRENT_RUNTIME_READINESS_REPORT.md`

## Migrations

None.

This phase uses existing `system_state`, `service_health`, and `runtime_cycles_v2` tables plus existing process-local stores.

## Verification

Commands run:

- `.venv\Scripts\python.exe -m pytest tests/test_runtime_readiness.py tests/test_runtime_health_truth.py tests/test_runtime_api.py tests/test_control_center_read_only_apis.py tests/test_truth_hardening.py`
- `npm test -- --run src/api/controlCenterClient.test.ts`
- `.venv\Scripts\python.exe -m py_compile app\control_center\runtime_readiness.py app\api\routes.py app\runtime\health_truth.py tests\test_runtime_readiness.py`
- `npm run build`
- In-process GET smoke for `/dashboard/api/v2/control/runtime-readiness`
- External GET to `http://127.0.0.1:8000/dashboard/api/v2/control/runtime-readiness`

Results:

- Python focused suite: `11 passed, 20 skipped`
- Skipped tests were Postgres-fixture dependent in this shell.
- Frontend endpoint client tests: `6 passed`
- Python compile: passed
- Frontend build: passed, with existing Vite large chunk warning
- In-process GET: `200`
- External localhost `:8000` GET: `404`, indicating the already-running server is not serving this updated code

In-process GET summary:

- `status = MISSING`
- `truth_state = UNKNOWN`
- `readiness_state = UNKNOWN`
- `runtime_life_state = UNKNOWN`
- `system_power_state = UNKNOWN`
- `scheduler_state = UNKNOWN`
- `supervisor_state = REGISTERED_NOT_RUNNING`
- `full_monitor_run_state = DIAGNOSTIC_IDLE`
- `full_monitor_run_label = DIAGNOSTIC_ONLY`
- method: `GET`

## Safety Checklist

- Did not activate SYSTEM ON.
- Did not activate PAPER.
- Did not activate SHADOW_LIVE.
- Did not activate SMALL_LIVE or live trading.
- Did not start Full Monitor Run.
- Did not call any POST action endpoint.
- Did not change trading, risk, execution, or paper behavior.
- Did not add migrations.
- Did not let Full Monitor Run imply runtime life.
- Missing runtime state does not enable trading.
- Missing runtime state is not initialized by the readiness endpoint.

## Risks

- Runtime Supervisor and Full Monitor Run status remain process-local by design and are labeled as such.
- The local `127.0.0.1:8000` process appears stale relative to this worktree and must be restarted separately before external HTTP verification can hit the new route.
- DB-backed readiness tests could not execute locally without the configured Postgres test fixture.

## Completion

Complete:

- Backend readiness service.
- Read-only Control Center endpoint.
- `/runtime/health` readiness overlay.
- Frontend endpoint wiring and operator display.
- Focused tests and build verification.
- Safety/reporting documentation.

Partial:

- External localhost GET against the currently running server returned 404 because that server is not updated.
- ChatGPT review is still required by the dispatch protocol before operational sign-off.

Safe to proceed:

- Safe to proceed to review and deploy/restart verification.
- Not safe to treat the already-running `:8000` process as updated until restarted.
