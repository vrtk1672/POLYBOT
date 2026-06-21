# Supervisor Life Path Report

## 1. Purpose

Phase 6 makes the normal life path observable:

SYSTEM ON -> Runtime Supervisor -> continuous read-only cycles -> freshness/readiness truth -> Control Center -> SYSTEM OFF cleanup.

This phase keeps Full Monitor Run separated as diagnostic-only and does not enable Paper Simulation, Shadow, or Live.

## 2. Current Reality Found

Before implementation, the active runtime was safe/stopped:

- system power: OFF
- runtime life: STOPPED
- paper simulation: OFF
- paper readiness: BLOCKED
- supervisor: process-local and not running
- Full Monitor Run: process-local diagnostic status only

Existing SYSTEM ON already turned power ON, forced/kept DATA_ONLY, and started `RuntimeSupervisorService`. Existing SYSTEM OFF disabled paper simulation, stopped the supervisor, and turned power OFF.

## 3. Existing Sources Reused

- `system_state` for system power and transition timestamps.
- `DEFAULT_RUNTIME_SUPERVISOR_STORE` for process-local supervisor heartbeat and cycle counters.
- `runtime_cycles_v2` for scheduler/runtime cycle history.
- `event_log.stored_at` for event updates since SYSTEM ON.
- `paper_eligibility_candidates.updated_at` for candidate updates since SYSTEM ON.
- `RuntimeReadinessService` for runtime readiness.
- `PaperReadinessService` for paper readiness.
- `DEFAULT_FULL_MONITOR_RUN_STORE` for diagnostic run state.

## 4. Files Inspected

- `app/control_center/runtime_supervisor.py`
- `app/control_center/action_service.py`
- `app/control_center/runtime_readiness.py`
- `app/control_center/paper_readiness.py`
- `app/control_center/full_monitor_run_service.py`
- `app/control_center/query_service.py`
- `app/services/system_power.py`
- `app/runtime/state_governor.py`
- `app/runtime/health_truth.py`
- `app/scheduler.py`
- `app/main.py`
- `app/api/routes.py`
- `app/api/runtime_routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_control_center_runtime_supervisor.py`
- `tests/test_runtime_readiness.py`
- `tests/test_runtime_health_truth.py`
- `tests/test_control_center_read_only_apis.py`
- `tests/test_control_center_paper_simulation.py`

## 5. Files Changed

- `app/control_center/supervisor_life_path.py`
- `app/control_center/action_service.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_supervisor_life_path.py`
- `tests/test_control_center_runtime_supervisor.py`
- `tests/test_control_center_read_only_apis.py`
- `docs/SUPERVISOR_LIFE_PATH_REPORT.md`

## 6. APIs Changed

Added:

- `GET /dashboard/api/v2/control/supervisor-life-path`

The endpoint returns supervisor life state, system power, runtime life state, heartbeat, cycle state, supervisor cycle count, event/candidate/readiness update flags, Full Monitor Run diagnostic label, blockers, warnings, sources, and artifact counts.

Updated:

- `POST /dashboard/api/v2/control/actions/system-on` now passes optional `interval_seconds` into `RuntimeSupervisorStartRequest`.

## 7. Frontend Changes

- Added `supervisorLifePath` endpoint key.
- Added `useSupervisorLifePathQuery`.
- Added 3 second refresh policy.
- Added a Control Center "Supervisor Life Path" panel showing:
  - supervisor life
  - system power
  - heartbeat age
  - cycle state
  - supervisor/scheduler cycles
  - events updated
  - candidates updated
  - runtime/paper readiness update flags
  - paper readiness
  - Full Monitor Run as `DIAGNOSTIC_ONLY`
  - life-path blockers

No mock data was introduced.

## 8. Tests Added

Added `tests/test_supervisor_life_path.py` covering:

- power OFF returns STOPPED/BLOCKED truth with `SYSTEM_POWER_OFF`
- running supervisor exposes fresh heartbeat and cycles
- Full Monitor Run is diagnostic-only and does not make supervisor alive
- stale supervisor heartbeat becomes STALE
- registered-not-running supervisor is not ALIVE
- endpoint shape and GET read-only artifact safety

Updated related tests:

- `tests/test_control_center_runtime_supervisor.py` verifies SYSTEM ON passes interval to supervisor.
- `tests/test_control_center_read_only_apis.py` includes supervisor life path in read-only contract coverage and narrows mutating-action exposure checks to explicit action paths.
- `frontend/control-center/src/api/controlCenterClient.test.ts` includes the new endpoint and refresh policy.

## 9. Tests Run And Results

Backend:

- `.venv\Scripts\python.exe -m pytest tests/test_supervisor_life_path.py -q`
  - Result: `6 passed in 33.46s`
- `.venv\Scripts\python.exe -m pytest tests/test_control_center_runtime_supervisor.py tests/test_runtime_readiness.py tests/test_runtime_health_truth.py tests/test_control_center_read_only_apis.py tests/test_control_center_paper_simulation.py -q`
  - Result: `33 passed in 63.05s`
- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed

Frontend:

- `npm run typecheck`
  - Result: passed
- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed (3), 18 passed (18)`
- `npm run build`
  - Result: passed; Vite reported existing chunk-size warning for a 595.58 kB JS chunk.

## 10. Deployment/Restart Results

Port 8000 owner:

- `docker compose ps` confirmed `polybot_api` serves `0.0.0.0:8000->8000/tcp`.
- Windows listener is WSL relay for the Docker-published port.

Deployment action:

- `docker compose build api`
  - Result: built `polybot_server-api`
- `docker compose up -d --no-deps api`
  - Result: recreated only `polybot_api`

## 11. Controlled SYSTEM ON Smoke Procedure

Baseline GET verification before SYSTEM ON:

- `GET /healthz`: 200, `status=ok`
- `GET /runtime/health`: 200, `runtime_life_state=STOPPED`
- `GET /dashboard/api/v2/control/runtime-readiness`: 200, `runtime_life_state=STOPPED`
- `GET /dashboard/api/v2/control/paper-readiness`: 200, `paper_readiness_state=BLOCKED`, `paper_simulation_state=OFF`
- `GET /dashboard/api/v2/control/candidate-explanations`: 200, stale/blocked candidate truth
- `GET /dashboard/api/v2/control/eligible-intent-bridge`: 200, stale/blocked bridge truth
- `GET /dashboard/api/v2/control/supervisor-life-path`: 200, `supervisor_life_state=STOPPED`, blockers included `SYSTEM_POWER_OFF`
- `GET /dashboard/api/v2/control/overview`: 200
- `GET /dashboard/api/v2/control/full-monitor-run`: 200, no active run
- `GET /dashboard/api/v2/control/runtime-supervisor`: 200, no running supervisor

Action:

- `POST /dashboard/api/v2/control/actions/system-on`
  - actor: `codex_phase6`
  - interval_seconds: `30`
  - Result: `ACCEPTED`
  - Paper Simulation remained `DISABLED`.
  - Live/shadow remained disabled.
  - Full Monitor Run was not started.

During smoke:

- `GET /dashboard/api/v2/control/supervisor-life-path`: 200
  - `supervisor_life_state=ALIVE`
  - `supervisor_state=ALIVE`
  - `cycle_state=CYCLE_COMPLETED`
  - `cycles_completed_since_system_on=3`
  - `events_updated=true`
  - `candidates_updated=false`
  - warning: `CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON`
  - warning: `PAPER_SIMULATION_OFF`
- `GET /dashboard/api/v2/control/paper-readiness`: 200
  - `paper_readiness_state=BLOCKED`
  - `paper_simulation_state=OFF`
  - blockers included `PAPER_SIMULATION_OFF`

Cleanup:

- `POST /dashboard/api/v2/control/actions/system-off`
  - Result: `ACCEPTED`
  - Supervisor stopped cleanly.
  - Paper Simulation remained OFF.

Final GET verification after SYSTEM OFF:

- `GET /healthz`: 200
- `GET /runtime/health`: 200, `runtime_life_state=STOPPED`
- `GET /dashboard/api/v2/control/runtime-readiness`: 200, `runtime_life_state=STOPPED`, blockers include `SYSTEM_POWER_OFF`
- `GET /dashboard/api/v2/control/supervisor-life-path`: 200, `supervisor_life_state=STOPPED`, `supervisor_state=STOPPED`
- `GET /dashboard/api/v2/control/paper-readiness`: 200, `paper_readiness_state=BLOCKED`, `paper_simulation_state=OFF`
- `GET /dashboard/api/v2/control/full-monitor-run`: 200, no active run
- `GET /dashboard/api/v2/control/runtime-supervisor`: 200, last-known stopped supervisor report

## 12. Before/After Runtime States

Before:

- system power: OFF
- runtime life: STOPPED
- supervisor life: STOPPED
- paper readiness: BLOCKED
- paper simulation: OFF

During SYSTEM ON:

- system power: ON
- supervisor life: ALIVE
- supervisor cycles completed: 3 observed by life-path endpoint, 4 total by final stop report
- runtime readiness: STALE due stale DB successful runtime cycle, with explicit blocker
- paper readiness: BLOCKED because Paper Simulation stayed OFF

After SYSTEM OFF:

- system power: OFF
- runtime life: STOPPED
- supervisor life: STOPPED
- paper readiness: BLOCKED
- paper simulation: OFF

## 13. Before/After Data Safety Counts

Before:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

During SYSTEM ON:

- all counts unchanged

After SYSTEM OFF:

- `paper_intents`: 20
- `paper_orders`: 12
- `paper_fills`: 9
- `paper_positions`: 12
- `paper_position_closes`: 9
- `live_orders`: 0
- `orders_v2`: 1
- `fills_v2`: 1
- `positions`: 0

## 14. Supervisor Cycles Observed

- Supervisor life-path endpoint observed 3 completed supervisor cycles during polling.
- SYSTEM OFF action report showed 4 completed supervisor cycles before stop.
- The supervisor ran in DATA_ONLY monitoring mode.
- Paper execution module was skipped because Paper Simulation was disabled.
- Live execution module was skipped and forbidden.

## 15. Events/Candidates/Readiness Updates Observed

- Events updated: yes.
- Candidates updated: no; explicitly reported as `CANDIDATES_NOT_UPDATED_SINCE_SYSTEM_ON`.
- Runtime readiness updated: yes, but remained stale/not ready because DB runtime successful cycle truth was stale.
- Paper readiness updated: yes, remained BLOCKED because Paper Simulation was OFF.

## 16. Full Monitor Run Diagnostic-Only Verification

- `GET /dashboard/api/v2/control/full-monitor-run` stayed no-active-run/missing.
- Full Monitor Run was not started.
- Supervisor life was proven through `RuntimeSupervisorService`, not Full Monitor Run.
- `full_monitor_run_label` is `DIAGNOSTIC_ONLY`.

## 17. SYSTEM OFF Cleanup Result

SYSTEM OFF completed through the official action endpoint. Final runtime truth:

- system power: OFF
- supervisor state: STOPPED
- runtime readiness: STOPPED/NOT_READY
- paper readiness: BLOCKED
- paper simulation: OFF
- no artifact counts changed

## 18. Remaining Risks

- Supervisor heartbeat and cycle counters are process-local. After API restart, life-path truth can only report last-known DB cycles plus no active process-local supervisor.
- Candidate updates did not occur during the controlled smoke. The new endpoint reports this explicitly, but a later phase should connect or verify the normal candidate update producer path under SYSTEM ON.
- Runtime readiness still depends on DB `runtime_cycles_v2`; during smoke it remained `STALE` because no fresh successful scheduler runtime cycle was observed.
- Some read-only supervisor modules remain skipped because safe monitor endpoints are absent for orderbook/news/whale/social.

## 19. Next Recommended Phase

Harden the SYSTEM ON data producer path so fresh scheduler/runtime cycles update `runtime_cycles_v2` and candidate refresh truth, without relying on Full Monitor Run and without enabling Paper Simulation.
