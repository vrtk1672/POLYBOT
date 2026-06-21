# Stage 27 Unified System ON/OFF Runtime Supervisor Report

Generated: 2026-06-11

## Summary

Stage 27 implements the Control Center `SYSTEM ON` / `SYSTEM OFF` lifecycle as a real continuous DATA_ONLY runtime supervisor.

`SYSTEM ON` now turns system power ON through the State Governor, ensures DATA_ONLY safe monitoring mode, and starts a single in-process supervisor loop. `SYSTEM OFF` stops the supervisor and turns system power OFF. `KILL` stops the supervisor before activating kill state. No live trading, paper execution, order placement, fills, or position mutation are enabled by this phase.

## Dispatch Classification

- Executor: Codex
- Task mode: `CONTROLLED_RUNTIME_FEATURE_WITH_BROWSER_VERIFICATION`
- Risk level: HIGH
- Review requirements: Codex review complete; ChatGPT review required by POLYBOT dispatch protocol
- Reason: touches runtime control lifecycle and continuous background monitoring semantics

## Changed Files

- `app/control_center/runtime_supervisor.py`
- `app/control_center/action_service.py`
- `app/control_center/query_service.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/api/useControlCenterQueries.test.tsx`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/runtimeSupervisor.test.tsx`
- `tests/test_control_center_runtime_supervisor.py`
- `docs/STAGE_27_UNIFIED_SYSTEM_ON_OFF_RUNTIME_SUPERVISOR_REPORT.md`

## Runtime Behavior

- `SYSTEM ON` starts DATA_ONLY continuous monitoring.
- Supervisor cycles use the same safe read-only module envelope as Full Monitor Run.
- The supervisor is idempotent: repeated `SYSTEM ON` does not create overlapping loops.
- `SYSTEM OFF` requests stop and writes a session report.
- `KILL` stops/marks the supervisor killed and blocks restart while kill state is active.
- The supervisor status is exposed at:
  - `/dashboard/api/v2/control/runtime-supervisor`
- Control Center overview now lists the runtime-supervisor endpoint.
- Dashboard polling includes the supervisor heartbeat every 3 seconds.

## Safety

Execution remains disabled:

- `execution_enabled=false`
- `paper_execution_enabled=false`
- `paper_orders=0` in supervisor summaries
- `paper_fills=0` in supervisor summaries
- `positions_updated=0` in supervisor summaries

Database artifact check for rows created/opened after Stage 27 browser verification began at `2026-06-10T23:09:29+00:00`:

- `paper_orders.created_at_since_stage27=0`
- `paper_fills.created_at_since_stage27=0`
- `paper_positions.opened_at_since_stage27=0`
- `orders_v2.created_at_since_stage27=0`
- `fills_v2.created_at_since_stage27=0`
- `positions.opened_at_since_stage27=0`

## Migrations

None.

Stage 27 uses in-memory process state plus existing Control Center/system state tables and existing read-only dashboard data.

## Browser Verification

Browser audit artifacts:

- `run_reports/control_center_ui_audit_stage27/screenshots/initial-state.png`
- `run_reports/control_center_ui_audit_stage27/screenshots/system-on-supervisor-running.png`
- `run_reports/control_center_ui_audit_stage27/screenshots/system-off-supervisor-stopped.png`
- `run_reports/control_center_ui_audit_stage27/raw/audit-summary.json`
- `run_reports/control_center_ui_audit_stage27/raw/supervisor-flow.json`
- `run_reports/control_center_ui_audit_stage27/raw/console.json`
- `run_reports/control_center_ui_audit_stage27/raw/network.json`
- `run_reports/control_center_ui_audit_stage27/traces/supervisor-flow-trace.json`

Browser result:

- Control Center loaded at `http://127.0.0.1:8000/control-center`
- Initial state established with system power OFF
- Clicked `SYSTEM ON` from the UI
- Supervisor reached `RUNNING`
- System power reached `ON`
- Mode remained `DATA_ONLY`
- Waited through 2 completed supervisor cycles
- Failed cycles: 0
- Clicked `SYSTEM OFF` from the UI
- Supervisor reached `STOPPED`
- System power reached `OFF`
- Browser console errors: 0
- Observed Control Center API network failures: 0
- Wrong base URL requests in recorded Control Center API probes: 0

Supervisor session report:

- `run_reports/control_center_supervisor_sessions/runtime_supervisor_05df5bc6840e4bb5abfce02a7f7d07dd.md`
- `run_reports/control_center_supervisor_sessions/runtime_supervisor_05df5bc6840e4bb5abfce02a7f7d07dd.json`

## Tests Run

- `.venv\Scripts\python.exe -m py_compile app/control_center/runtime_supervisor.py app/control_center/action_service.py app/control_center/query_service.py app/api/routes.py`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_runtime_supervisor.py tests/test_control_center_actions.py tests/test_control_center_full_monitor_run.py -q`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_runtime_supervisor.py tests/test_control_center_actions.py tests/test_control_center_full_monitor_run.py tests/test_control_center_stage17_safety_certification.py -q`
- `$files = Get-ChildItem tests -Filter 'test_control_center_*.py' | ForEach-Object { $_.FullName }; .\.venv\Scripts\python.exe -m pytest @files -q`
- `.venv\Scripts\python.exe -m pytest tests/test_ai_context_router.py -q`
- `npm test -- runtimeSupervisor --run`
- `npm test -- --run`
- `npm run typecheck`
- `npm run build`
- `docker compose build api`
- `docker compose build test`
- `docker compose up -d api`
- Endpoint smoke checks:
  - `GET /control-center`
  - `GET /dashboard/api/v2/control/overview`
  - `GET /dashboard/api/v2/control/full-monitor-run`
  - `GET /dashboard/api/v2/control/runtime-supervisor`

## Results

- Backend targeted tests: PASS
- Control Center backend regression tests: PASS
- AI router tests: PASS with DB-gated skips
- Frontend focused tests: PASS
- Full frontend tests: PASS
- Frontend typecheck: PASS
- Frontend build: PASS with existing Vite large chunk warning
- Docker API build: PASS
- Docker test build: PASS
- API container health: PASS
- Browser verification: PASS

## Risks

- Supervisor state is process-local. Restarting the API resets in-memory supervisor session visibility, while system power remains persisted in Postgres.
- Session reports generated inside Docker require volume mapping or copying out if host persistence is needed.
- The supervisor currently reuses the Full Monitor Run read-only module envelope; future runtime phases should move heavier runtime ownership into a dedicated scheduler/service layer before enabling paper execution.

## Rollback Notes

Rollback is file-level only:

- Remove `app/control_center/runtime_supervisor.py`
- Remove the runtime-supervisor route and Control Center endpoint wiring
- Revert `ControlCenterActionService` to only toggle system power for `SYSTEM ON` / `SYSTEM OFF`
- Remove frontend supervisor heartbeat UI and related tests

No migrations or database rollback are required.

## Definition Of Done

- SYSTEM ON starts continuous DATA_ONLY monitoring: complete
- SYSTEM OFF stops continuous monitoring: complete
- KILL stops/blocks supervisor: complete
- No execution artifacts created: complete
- Runtime supervisor status endpoint: complete
- Dashboard heartbeat truth UI: complete
- Tests and browser verification: complete

## Safe To Proceed

YES for DATA_ONLY monitoring operation and ChatGPT review.

NO for PAPER execution, SHADOW_LIVE, SMALL_LIVE, ATTACK_MODE, live orders, paper fills, or position mutation. Those remain out of scope and blocked.
