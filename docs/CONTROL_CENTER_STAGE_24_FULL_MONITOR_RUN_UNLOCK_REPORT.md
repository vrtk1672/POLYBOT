# POLYBOT Control Center Stage 24 Full Monitor Run Unlock Report

## 1. Short Summary

Stage 24 fixed the Control Center unlock path for Full Monitor Run (FMR). The operator can now press `SYSTEM ON` from the previous `PAPER + OFF` locked state, safely transition into `DATA_ONLY + ON`, and then start a bounded read-only Full Monitor Run.

## 2. Current Mode/State Found

Before the fix, Docker runtime state was:

- `current_mode`: `PAPER`
- `system_power`: `OFF`
- `kill_switch_active`: `false`
- all runtime permissions: `false`

After the browser-verified flow:

- `current_mode`: `DATA_ONLY`
- `system_power`: `ON`
- `can_collect_data`: `true`
- `can_open_paper_positions`: `false`
- `can_create_live_orders`: `false`
- `can_run_live_engine`: `false`

## 3. Why FMR Was Locked

`START FULL MONITOR RUN` correctly asks the State Governor whether `COLLECT_DATA` is allowed. In the persisted `PAPER + OFF` state, `COLLECT_DATA` was denied because system power was off. `SYSTEM ON` previously toggled power only and did not provide a safe monitoring-mode transition path.

## 4. Fix Implemented

The Control Center `system-on` action now asks the State Governor to enter `DATA_ONLY` safe monitoring mode before turning system power on. This is scoped to the audited Control Center action path and does not bypass FMR governor checks.

KILL remains protected: `system-on` refuses to resume from KILL mode or an active kill switch.

## 5. Files Created

- `docs/CONTROL_CENTER_STAGE_24_FULL_MONITOR_RUN_UNLOCK_REPORT.md`

## 6. Files Changed

- `app/control_center/action_service.py`
- `tests/test_control_center_actions.py`
- `tests/test_control_center_full_monitor_run.py`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `frontend/control-center/src/pages/fullMonitorRun.test.tsx`
- `run_reports/control_center_ui_audit/audit-control-center.mjs`

## 7. State Governor / Mode Logic Before and After

Before:

- `system-on` only toggled power.
- The persisted mode remained `PAPER`.
- FMR could remain locked depending on prior persisted state and power.

After:

- `system-on` enters `DATA_ONLY` through `StateGovernor.request_mode_change`.
- Power is turned on only after the safe monitoring transition.
- FMR still calls `StateGovernor.can_execute(COLLECT_DATA)`.
- No trading permission is granted by the unlock path.

## 8. SYSTEM ON Behavior Before and After

Before:

- `SYSTEM ON` did not establish a safe monitoring mode.
- UI guidance could leave the operator unclear about the next valid step.

After:

- `SYSTEM ON` reports safe monitoring mode.
- UI guidance says current mode is `DATA_ONLY`, power is `ON`, and the next step is `START FULL MONITOR RUN`.

## 9. FMR Behavior Before and After

Before:

- Starting FMR from `PAPER + OFF` was locked by mode/power.

After:

- From `DATA_ONLY + ON`, FMR is accepted and completes.
- Latest verified run: `full_monitor_run_45381694071d42cc944bf8a36425c02c`
- Status: `COMPLETED`
- Cycles completed: `1`
- Opportunities found: `20`
- Paper orders: `0`
- Paper fills: `0`
- Positions updated: `0`

## 10. Backend Tests Added/Updated

- Added safe `SYSTEM ON` transition test to `DATA_ONLY`.
- Added KILL resume refusal test.
- Added power-off FMR block test.
- Added post-safe-transition FMR allow test with zero execution artifacts.

## 11. Frontend Tests Added/Updated

- Added cockpit recovery test for `SYSTEM ON` then completed FMR.
- Updated locked guidance text expectations.
- Increased two slow interaction test timeouts to avoid suite-load flakes.

## 12. Tests Run and Exact Results

- `.venv\Scripts\python.exe -m pytest tests/test_control_center_actions.py tests/test_control_center_full_monitor_run.py tests/test_control_center_stage17_safety_certification.py -q`
  - Result: `26 passed in 7.95s`
- all `tests/test_control_center_*.py`
  - Result: `45 passed in 18.40s`
- `npm test`
  - Result: `14 passed (14), 83 passed (83)`
- `npm run typecheck`
  - Result: passed
- `npm run build`
  - Result: passed with existing Vite chunk-size warning

## 13. Docker Rebuild Result

- `docker compose build api`: passed
- `docker compose up -d api`: passed
- `docker compose ps api`: `Up ... (healthy)`
- `/control-center`: HTTP `200 OK` by `curl.exe`

## 14. Browser Playwright Verification

Audit command:

```powershell
$env:CONTROL_CENTER_AUDIT_DIR='run_reports/control_center_ui_audit_stage24'
node run_reports/control_center_ui_audit/audit-control-center.mjs
Remove-Item Env:\CONTROL_CENTER_AUDIT_DIR
```

Final result:

- `fullMonitorRunFlow`: `PASS`
- `consoleErrorCount`: `0`
- `networkFailureCount`: `0`
- `wrongBaseUrlRequestCount`: `0`

## 15. Screenshots / Evidence Links

- `run_reports/control_center_ui_audit_stage24/screenshots/system-on-result.png`
- `run_reports/control_center_ui_audit_stage24/screenshots/full-monitor-run-result.png`
- `run_reports/control_center_ui_audit_stage24/raw/full-monitor-run-flow.json`
- `run_reports/control_center_ui_audit_stage24/raw/audit-summary.json`
- `run_reports/control_center_ui_audit_stage24/raw/console.json`
- `run_reports/control_center_ui_audit_stage24/raw/network.json`

## 16. Console / Network Findings

- Browser console errors: `0`
- Network failures: `0`
- Wrong base URL requests: `0`
- Control Center API responses observed as `200 OK`

## 17. Safety Checklist

- No live trading enabled.
- No live orders created.
- No paper orders created.
- No paper fills created.
- No positions updated by FMR.
- No backend API bypass added.
- No migrations run.
- No trading, risk, execution, capital, or live engine logic loosened.
- KILL cannot be resumed by `SYSTEM ON`.

## 18. Remaining Issues

- Overview remains `PARTIAL` / `REFRESH_REQUIRED` because source truth is stale or partial; this is correctly displayed, not painted green.
- Scheduler service still shows historical `BLOCKED_BY_MODE` events in source rows; this was not changed.
- Vite still warns about a chunk larger than 500 kB; this is outside Stage 24 scope.

## 19. Phase Status

GREEN.

## 20. Can Continue

YES, after ChatGPT review.

## 21. Recommended Next Step

Run the requested ChatGPT review on Stage 24, then proceed to the next browser audit or operator-flow hardening phase.
