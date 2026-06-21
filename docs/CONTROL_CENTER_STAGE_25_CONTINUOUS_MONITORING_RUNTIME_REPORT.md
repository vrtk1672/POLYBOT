# POLYBOT Control Center Stage 25 Continuous Monitoring Runtime Report

## 1. Short Summary

Stage 25 implemented a bounded, DATA_ONLY continuous monitoring runtime for the Control Center Full Monitor Run flow. The cockpit can now start a read-only monitoring run with duration and interval, display live/terminal run state, stop an active run, and expose an end-of-run report path. No trading, execution, paper order/fill creation, position mutation, migrations, or backend trading logic changes were introduced.

Final browser verification status: GREEN.

## 2. Current Reality Before Stage 25

- Full Monitor Run was a synchronous one-shot service.
- In-process `FullMonitorRunStore` held current/latest run state.
- `STOP CURRENT RUN` existed, but the start request blocked until completion, so there was no meaningful active run window to stop.
- The Operator Cockpit already consumed the Full Monitor Run query.
- Run state did not survive API process restart.
- Stage 24 browser audit proved the cockpit could call safe action wrappers, but not a real continuous runtime loop.
- `docs/POLYBOT_CODEX_PROMPT_STANDARD.md` was requested in context but was not present.

## 3. Architecture Decision

Implemented the smallest safe runtime: an in-process daemon thread per active monitoring run, guarded by the existing State Governor and a single active-run store. This avoids migrations, avoids new runtime services, and keeps Stage 25 scoped to Control Center monitoring visibility.

Reports are written by the API process under `run_reports/control_center_monitor_runs`. In Docker verification, those files exist inside `polybot_api` at `/app/run_reports/control_center_monitor_runs`; the path is reported by API response and UI.

## 4. Backend Runtime Changes

- Added `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `COMPLETED`, and `FAILED` visibility states.
- Added `duration_minutes`, `interval_seconds`, `remaining_seconds`, `next_cycle_in_seconds`, `events_seen`, module totals, report paths, `safety_mode`, and `execution_enabled` fields.
- Added background scheduling with an interruptible stop event.
- Enforced `DATA_ONLY` mode for Stage 25 monitoring.
- Preserved execution counters as zero for this monitor runtime.
- Added Markdown and JSON end-of-run reports.
- Kept all monitor modules read-only; unsafe modules are marked `SKIPPED`.

## 5. Frontend Cockpit Changes

- Renamed the operator action to `START MONITORING RUN`.
- Added interval input and validation.
- Added active-run detection and conditional `STOP CURRENT RUN`.
- Displayed elapsed, remaining, next cycle, cycles, markets, events, opportunities, no-trades, warnings, errors, execution enabled, and report path.
- Updated Full Monitor Run polling to 3000 ms.
- Kept action calls routed through safe Control Center wrappers only.

## 6. Run Scheduler / Loop Behavior

- First cycle runs immediately.
- Subsequent cycles wait for `interval_seconds`.
- Runtime stops after `duration_minutes` or an explicit stop request.
- Only safe read-only envelope modules execute.
- Paper execution and live execution are skipped and recorded as skipped modules.

## 7. Stop Behavior

`STOP CURRENT RUN` marks active runs as `STOPPING`, signals the stop event, and allows the worker to exit cleanly. It does not kill processes, mutate trading state, or call execution systems.

## 8. End-of-Run Report Behavior

The worker writes both Markdown and JSON reports at completion, stop, or failure. The final verified Docker run wrote:

- `/app/run_reports/control_center_monitor_runs/full_monitor_run_aba8f42567df4567bbb4a593b1ae5215.md`
- `/app/run_reports/control_center_monitor_runs/full_monitor_run_aba8f42567df4567bbb4a593b1ae5215.json`

API/UI report path:

- `run_reports/control_center_monitor_runs/full_monitor_run_aba8f42567df4567bbb4a593b1ae5215.md`

## 9. Files Created

- `docs/CONTROL_CENTER_STAGE_25_CONTINUOUS_MONITORING_RUNTIME_REPORT.md`
- Browser audit artifacts under `run_reports/control_center_ui_audit_stage25_verified/`
- Docker API container run reports under `/app/run_reports/control_center_monitor_runs/`

## 10. Files Changed

- `app/control_center/full_monitor_run.py`
- `app/control_center/full_monitor_run_service.py`
- `app/control_center/action_contract.py`
- `app/control_center/action_service.py`
- `frontend/control-center/src/api/controlCenterActions.ts`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/ControlActionsPanel.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `frontend/control-center/src/pages/controlActions.test.tsx`
- `frontend/control-center/src/pages/fullMonitorRun.test.tsx`
- `frontend/control-center/src/pages/stage17Safety.test.tsx`
- `tests/test_control_center_full_monitor_run.py`
- `tests/test_control_center_actions.py`
- `tests/test_control_center_stage17_safety_certification.py`
- `run_reports/control_center_ui_audit/audit-control-center.mjs`

## 11. Tests Added/Updated

- Backend tests for interval validation, DATA_ONLY-only enforcement, active-run blocking, report writing, endpoint status shape, action wiring, and safety certification compatibility.
- Frontend tests for `START MONITORING RUN`, interval payloads, stop visibility, report path visibility, and updated polling policy.
- Browser audit script updated to verify exact run ID completion and report path.

## 12. Tests Run and Exact Results

- `.\.venv\Scripts\python.exe -m pytest tests/test_control_center_full_monitor_run.py tests/test_control_center_actions.py tests/test_control_center_stage17_safety_certification.py -q`
  - Result: `30 passed in 8.16s`
- `.\.venv\Scripts\python.exe -m pytest @tests -q` for all `tests/test_control_center_*.py`
  - Result: `49 passed in 47.62s`
- `npm test`
  - Result: `14 passed`, `83 passed`
- `npm run typecheck`
  - Result: passed
- `npm run build`
  - Result: passed
  - Note: Vite emitted a non-failing chunk-size warning for a `570.10 kB` JS chunk.
- `py_compile` for changed backend modules
  - Result: passed

## 13. Docker Rebuild Result

- `docker compose build api`
  - Result: passed
- `docker compose up -d api`
  - Result: passed
- `docker compose ps api`
  - Result: `polybot_api` healthy, port `8000` mapped.

## 14. Browser Playwright Verification

Final command:

```powershell
$env:CONTROL_CENTER_AUDIT_DIR='run_reports/control_center_ui_audit_stage25_verified'; node run_reports/control_center_ui_audit/audit-control-center.mjs; Remove-Item Env:\CONTROL_CENTER_AUDIT_DIR
```

Result:

- `fullMonitorRunFlow`: `PASS`
- `pageCount`: `15`
- `consoleErrorCount`: `0`
- `networkFailureCount`: `0`
- `wrongBaseUrlRequestCount`: `0`

The strict audit captured the start action response run ID and polled `/dashboard/api/v2/control/full-monitor-run` until that specific run completed with a report path.

## 15. Screenshots / Evidence Links

- `run_reports/control_center_ui_audit_stage25_verified/screenshots/initial-cockpit.png`
- `run_reports/control_center_ui_audit_stage25_verified/screenshots/system-on-result.png`
- `run_reports/control_center_ui_audit_stage25_verified/screenshots/monitoring-running.png`
- `run_reports/control_center_ui_audit_stage25_verified/screenshots/monitoring-completed.png`
- `run_reports/control_center_ui_audit_stage25_verified/screenshots/full-monitor-run-after.png`
- Raw flow: `run_reports/control_center_ui_audit_stage25_verified/raw/full-monitor-run-flow.json`
- Summary: `run_reports/control_center_ui_audit_stage25_verified/raw/audit-summary.json`

## 16. Generated Run Report Link

Docker container path:

- `/app/run_reports/control_center_monitor_runs/full_monitor_run_aba8f42567df4567bbb4a593b1ae5215.md`

API/UI path:

- `run_reports/control_center_monitor_runs/full_monitor_run_aba8f42567df4567bbb4a593b1ae5215.md`

Important: this report was generated inside the Docker API container, not mirrored to the host workspace during this verification.

## 17. Console / Network Findings

- Console errors: `0`
- Page errors: `0`
- Network failures: `0`
- Wrong base URL requests: `0`
- `/control-center` returned HTTP `200`
- `/dashboard/api/v2/control/overview` returned JSON
- `/dashboard/api/v2/control/full-monitor-run` returned JSON

## 18. Safety Checklist

- Live trading enabled: NO
- Paper execution enabled by Stage 25: NO
- Orders created by monitor run: NO
- Fills created by monitor run: NO
- Positions updated by monitor run: NO
- Trading/risk/execution/capital logic changed: NO
- Backend migrations added/run: NO
- State Governor bypassed: NO
- DATA_ONLY enforced: YES
- Unsafe modules skipped: YES
- End-of-run report generated: YES

## 19. Remaining Issues

- Run state and generated reports remain in-process/container-local. A Docker API restart clears in-memory latest/current state, and reports are not persisted to host unless a mount is added in a later reviewed phase.
- Some skipped module warning text still references Stage 16 wording; behavior is correct, but wording should be cleaned in a later documentation/UI polish phase.
- Vite build still has a non-failing large chunk warning.
- Cockpit overall health remains `PARTIAL` / `REFRESH_REQUIRED` because source truth is partially stale; this is expected and not painted green.

## 20. Phase Status: GREEN

Stage 25 implementation and verification passed.

## 21. Can Continue: YES

Safe to proceed to ChatGPT/operator review. Do not proceed to broader runtime persistence, mounts, or additional automation without review.

## 22. Recommended Next Step

ChatGPT review of Stage 25, with special attention to the in-process scheduler choice, container-local report storage, and whether Stage 26 should persist run reports to host/DB.
