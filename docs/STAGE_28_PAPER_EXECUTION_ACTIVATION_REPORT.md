# POLYBOT Stage 28 Paper Execution Activation Report

Generated: 2026-06-11

## Dispatch Classification

- Recommended executor: Codex
- Task mode: CONTROLLED_PAPER_EXECUTION_FEATURE_WITH_BROWSER_VERIFICATION
- Risk level: HIGH
- Codex review required: YES
- ChatGPT review required: YES
- Reason: touches paper order/fill/position creation controls, runtime supervisor behavior, State Governor gating, and operator activation paths.

## Summary

Stage 28 adds explicit Control Center paper-simulation activation without enabling live trading.

SYSTEM ON remains a DATA_ONLY monitoring action. Paper simulation now requires a separate PAPER SIMULATION ON action, persisted through State Governor metadata and visible through a dedicated truth endpoint. When enabled, the runtime supervisor calls the existing canonical paper services only:

- `PaperIntentGateService.build_intents`
- `PaperExecutionService.run_execution`
- `PaperExitLoopService.run_exit_loop`
- `PaperExitLoopService.get_pnl_dashboard_summary`

No new paper execution logic was invented in the Control Center. No live execution path was added.

## Changed Files

- `app/control_center/paper_simulation.py`
- `app/control_center/action_contract.py`
- `app/control_center/action_service.py`
- `app/control_center/query_service.py`
- `app/control_center/runtime_supervisor.py`
- `app/api/routes.py`
- `frontend/control-center/src/api/controlCenterActions.ts`
- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `frontend/control-center/src/pages/runtimeSupervisor.test.tsx`
- `tests/test_control_center_actions.py`
- `tests/test_control_center_runtime_supervisor.py`
- `tests/test_control_center_paper_simulation.py`

## Migrations

None.

Stage 28 reuses existing canonical paper tables and State Governor `system_state.metadata_json`:

- `paper_intents`
- `no_trade_log`
- `paper_execution_runs`
- `paper_exit_loop_runs`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_daily_pnl`
- `system_state`
- `system_state_history`

## API / Controls

New read endpoint:

- `GET /dashboard/api/v2/control/paper-simulation`

New action wrapper names:

- `enable-paper-simulation`
- `disable-paper-simulation`

Safety behavior:

- SYSTEM ON does not enable paper simulation.
- PAPER SIMULATION ON requires actor and reason.
- PAPER SIMULATION ON is locked if KILL is active, power is OFF, runtime mode is not DATA_ONLY, live trading settings are enabled, or State Governor does not allow `RUN_PAPER_SIMULATION`.
- PAPER SIMULATION OFF disables the paper switch.
- SYSTEM OFF and KILL force-disable paper simulation.
- Runtime supervisor stopped/off status clears paper execution flags.
- Live execution remains false throughout.

## Runtime Result

Final fixed-code run:

- Supervisor session: `runtime_supervisor_fb1f9d1f191d47c69a3d29ac8076f2fd`
- Cycles completed: 3
- Cycles failed: 0
- Final supervisor status: STOPPED
- Final system power: OFF
- Final runtime mode: DATA_ONLY
- Final paper simulation status: DISABLED
- Final paper execution enabled: false
- Live execution enabled: false
- Paper intents blocked: 80
- Paper orders created: 0
- Paper fills created: 0
- Paper positions opened: 0

The run is YELLOW, not GREEN: paper simulation executed, but no candidate passed the canonical paper gate. The paper execution service returned `NO_VALID_PAPER_INTENTS` with stale/missing trusted orderbook blockers. This is a safe `NO_TRADE`/blocked outcome.

Copied supervisor reports:

- `run_reports/control_center_supervisor_sessions_stage28/runtime_supervisor_fb1f9d1f191d47c69a3d29ac8076f2fd.md`
- `run_reports/control_center_supervisor_sessions_stage28/runtime_supervisor_fb1f9d1f191d47c69a3d29ac8076f2fd.json`

Browser artifacts:

- `run_reports/control_center_ui_audit_stage28/stage28_control_center_after_wait.png`
- `run_reports/control_center_ui_audit_stage28/stage28_money_view.png`
- `run_reports/control_center_ui_audit_stage28/stage28_after_system_off.png`
- `run_reports/control_center_ui_audit_stage28/stage28_final_stopped_ui.png`
- JSON/console artifacts in `run_reports/control_center_ui_audit_stage28/`

## Browser Verification

Verified in the in-app browser against `http://localhost:8000/control-center`:

- Opened Control Center.
- Clicked SYSTEM ON with actor `harel`, reason `stage 28 paper supervisor test`.
- Confirmed supervisor RUNNING in DATA_ONLY.
- Clicked PAPER SIMULATION ON with actor `harel`, reason `stage 28 paper simulation test`.
- Waited across multiple supervisor cycles.
- Verified paper simulation enabled and paper blockers visible.
- Verified runtime-supervisor `no_trade.logged` events for paper cycles.
- Verified Money view uses ledger/positions sources and did not show fake PnL.
- Verified browser console errors: 0.
- Clicked PAPER SIMULATION OFF.
- Clicked SYSTEM OFF.
- Verified final UI OFF/DISABLED state.
- Rebuilt API after a stopped-record flag consistency fix and verified final API state:
  - supervisor STOPPED
  - system power OFF
  - paper simulation DISABLED
  - paper execution enabled false
  - execution enabled false

## Tests Run

Backend:

```powershell
python -m py_compile app/control_center/paper_simulation.py app/control_center/action_service.py app/control_center/runtime_supervisor.py app/api/routes.py
python -m py_compile app/control_center/runtime_supervisor.py
docker compose --profile test run --build --rm test python -m pytest tests/test_control_center_paper_simulation.py tests/test_control_center_runtime_supervisor.py tests/test_control_center_actions.py -q
```

Frontend:

```powershell
npm run typecheck
npm run test -- src/api/controlCenterClient.test.ts src/pages/commandCenterRecovery.test.tsx src/pages/runtimeSupervisor.test.tsx src/pages/controlActions.test.tsx
npm run build
```

Docker / live verification:

```powershell
docker compose up -d --build api
Invoke-RestMethod http://localhost:8000/dashboard/api/v2/control/paper-simulation
Invoke-RestMethod http://localhost:8000/dashboard/api/v2/control/runtime-supervisor
```

## Results

- Backend targeted tests: 25 passed, 1 Starlette deprecation warning.
- Frontend focused tests: 19 passed.
- Frontend typecheck: passed.
- Frontend build: passed with existing Vite chunk-size warning.
- Docker API: rebuilt and healthy.
- Browser console: 0 errors, 0 warnings during audit.
- Final API state: stopped/off/paper-disabled/live-disabled.

## Risks

- The current live dataset has stale or already-consumed paper intents. Stage 28 therefore produced a safe blocker/no-trade result instead of a new paper order.
- Runtime report files generated inside the Docker container are process/container-local unless copied out. The final Stage 28 supervisor report was copied to the workspace.
- The overview source count still reports Control Center endpoint counts from its existing source map; this does not affect paper activation safety.

## Rollback Notes

To roll back Stage 28:

- Remove `app/control_center/paper_simulation.py`.
- Remove `enable-paper-simulation` and `disable-paper-simulation` from action contracts and UI action lists.
- Remove `/dashboard/api/v2/control/paper-simulation`.
- Revert runtime supervisor paper-cycle integration to the Stage 27 read-only behavior.
- Rebuild the Control Center frontend and API image.

No database rollback is required because no migration was added.

## Definition Of Done

- Explicit paper activation action exists and is separate from SYSTEM ON.
- State Governor remains the source of permission truth.
- Live trading remains disabled.
- Runtime supervisor calls only canonical paper services when explicitly enabled.
- Missing/stale candidate truth results in blocked/no-trade, not fabricated orders.
- Paper PnL/positions are shown only from canonical ledger/table sources.
- SYSTEM OFF/KILL disable paper simulation.
- Tests and browser verification completed.

## Safe To Proceed

Safe to proceed to ChatGPT review / human review.

Do not proceed to live trading. This stage is paper simulation only.
