# POLYBOT Control Center V1.5 Stage 16 Full Monitor Run Report

Date: 2026-06-08

## 1. Short Summary

Stage 16 is GREEN.

Implemented a safe, bounded, stoppable Full Monitor Run contract for `FULL_MONITOR_RUN`. Stage 16 activates `START FULL MONITOR RUN` and `STOP CURRENT RUN` through the existing Stage 15 Control Center action wrapper. The run performs one bounded read-only/evaluation-only monitoring pass over existing Control Center truth envelopes and reports unsafe or unavailable modules as `SKIPPED`.

No live trading, manual trade, risk override, disabled governance, engine budget editing, order/fill/position creation, paper execution, DB migration, or destructive DB action was added.

## 2. Current Reality Found

| Area | Reality |
| --- | --- |
| Existing run/cycle support | `runtime_cycles_v2` and `RuntimeCycleRepository` exist for runtime cycles, but not for a Control Center Full Monitor Run start/stop contract. |
| Existing State Governor | `StateGovernor` exists and is checked before start. KILL blocks start. Live-order permission also locks start. |
| Existing system power | Preserved from Stage 15; not changed by Full Monitor Run. |
| Existing action wrapper | Stage 15 wrapper existed and now routes `start-full-monitor-run` / `stop-current-run` to the new service. |
| Safe persistence choice | No migration was added. Stage 16 uses an in-process latest/current run store with generated `run_id` and `audit_id`. |
| Modules safely callable | Existing Stage 5/8 Control Center read-only envelopes: overview, live-flow, organs, closest-actionable, risk-evidence, lifecycle-governance, positions, pnl-ledger, no-trade, ai, logs, truth-state. |
| Modules skipped/not implemented | orderbook, news, whale, social, paper execution, live execution. |
| Frontend | Settings panel now shows active start/stop controls, duration, read-only run status, counters, audit id, warnings/errors, and module results. |
| Deviations | The run is synchronous and completes one bounded monitoring pass immediately. It does not start a background runtime loop. |

## 3. Files Created

| File |
| --- |
| `app/control_center/full_monitor_run.py` |
| `app/control_center/full_monitor_run_service.py` |
| `tests/test_control_center_full_monitor_run.py` |
| `frontend/control-center/src/pages/fullMonitorRun.test.tsx` |
| `docs/CONTROL_CENTER_STAGE_16_FULL_MONITOR_RUN_REPORT.md` |

## 4. Files Changed

| File | Change |
| --- | --- |
| `app/api/routes.py` | Added GET `/dashboard/api/v2/control/full-monitor-run`; action wrapper continues to handle start/stop. |
| `app/control_center/action_contract.py` | Added `max_cycles`; duration validation moved into service to return action envelopes. |
| `app/control_center/action_service.py` | Activated start/stop Full Monitor Run actions. |
| `app/control_center/__init__.py` | Exported Full Monitor Run types/service. |
| `tests/test_control_center_actions.py` | Updated Stage 15 regression for Stage 16 active start action. |
| `frontend/control-center/src/api/controlCenterEndpoints.ts` | Added read-only `fullMonitorRun` endpoint. |
| `frontend/control-center/src/api/refreshPolicy.ts` | Added 5s polling policy for run status. |
| `frontend/control-center/src/api/useControlCenterQueries.ts` | Added `useFullMonitorRunQuery`. |
| `frontend/control-center/src/api/controlCenterActions.ts` | Added optional `max_cycles` payload field. |
| `frontend/control-center/src/pages/ControlActionsPanel.tsx` | Activated start/stop, duration 1..60, run status/counter/module display. |
| `frontend/control-center/src/pages/controlActions.test.tsx` | Updated monitor action expectations. |
| `frontend/control-center/src/api/controlCenterClient.test.ts` | Updated endpoint map and refresh policy expectations. |
| `frontend/control-center/src/layout/Sidebar.tsx` | Updated stale copy from no runtime actions to gated actions. |

## 5. Files Deleted

None.

## 6. API / Action Matrix

| Action/API | Status | Safety | Notes |
| ---------- | ------ | ------ | ----- |
| `POST /dashboard/api/v2/control/actions/start-full-monitor-run` | Active | Requires actor/reason/duration; checks State Governor; KILL blocks; live-order permission locks; no live/paper execution called. | Returns action envelope with run result. |
| `POST /dashboard/api/v2/control/actions/stop-current-run` | Active | Requires actor/reason; safe no-op when no run exists; does not kill DB/services. | Returns action envelope with stop result. |
| `GET /dashboard/api/v2/control/full-monitor-run` | Active | Read-only Truth Contract envelope. | Shows current/latest in-process run status. |
| `RESET PAPER BALANCE` | LOCKED | unchanged from Stage 15. | No certified paper-only reset contract exists. |

## 7. Run Output Contract

| Field | Present? | Notes |
| ----- | -------- | ----- |
| `run_id` | YES | Generated for each run/stop response. |
| `status` | YES | `COMPLETED`, `STOPPED`, `REJECTED`, `LOCKED`, or `ERROR` as applicable. |
| `started_at` | YES | UTC ISO string. |
| `stopped_at` / `ended_at` | YES | Present when stopped/completed. |
| `requested_duration_minutes` | YES | Required for start; max 60. |
| `elapsed_seconds` | YES | Numeric. |
| `cycles_completed` | YES | Numeric; Stage 16 defaults to 1 bounded pass. |
| `markets_checked` | YES | Numeric from overview counters when available. |
| `events_created` | YES | Always 0; monitor run does not create events. |
| `opportunities_found` | YES | Numeric from closest-actionable counters when available. |
| `no_trades_logged` | YES | Numeric from no-trade read-only counters when available. |
| `paper_orders` | YES | Always 0; paper execution skipped. |
| `paper_fills` | YES | Always 0; paper execution skipped. |
| `positions_updated` | YES | Always 0; no position mutation. |
| `module_results` | YES | Includes `COMPLETED` read-only modules and `SKIPPED` unsafe/unavailable modules. |
| `errors` | YES | Array. |
| `warnings` | YES | Array. |
| `audit_id` | YES | Generated in-process audit id for accepted/stop responses. |

## 8. Module Execution Matrix

| Module | Status | Behavior |
| ------ | ------ | -------- |
| market scan | COMPLETED | Reads overview truth envelope only. |
| events | COMPLETED | Reads live-flow truth envelope only. |
| health | COMPLETED | Reads organ/service truth envelope only. |
| opportunity | COMPLETED | Reads closest-actionable truth envelope only. |
| risk | COMPLETED | Reads risk-evidence truth envelope only. |
| capital | COMPLETED | Reads overview-backed capital/source truth only. |
| positions | COMPLETED | Reads positions truth envelope only. |
| exit | COMPLETED | Reads lifecycle-governance/exit-adjacent truth only. |
| pnl | COMPLETED | Reads PnL ledger truth envelope only. |
| no-trade | COMPLETED | Reads no-trade truth envelope only. |
| AI | COMPLETED | Reads AI context truth envelope only. |
| logs | COMPLETED | Reads logs/errors truth envelope only. |
| memory | COMPLETED | Reads truth-state/memory-adjacent truth only. |
| orderbook | SKIPPED | No safe Control Center read-only monitor endpoint exists in Stage 16. |
| news | SKIPPED | No safe Control Center read-only monitor endpoint exists in Stage 16. |
| whale | SKIPPED | No safe Control Center read-only monitor endpoint exists in Stage 16. |
| social | SKIPPED | No safe Control Center read-only monitor endpoint exists in Stage 16. |
| paper execution | SKIPPED | Can create paper orders/fills; not called. |
| live execution | SKIPPED | Forbidden; never called. |

## 9. Tests Added

| Test File | Coverage |
| --- | --- |
| `tests/test_control_center_full_monitor_run.py` | Contract shape, required actor/reason/duration, invalid duration envelope rejection, KILL block, skipped modules, zero execution counters, stop behavior, action wrapper activation, status endpoint Truth Contract. |
| `frontend/control-center/src/pages/fullMonitorRun.test.tsx` | Start/stop UI gates, wrapper-only POSTs, run counters, skipped modules, forbidden-control absence. |

## 10. Tests Run and Exact Results

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest tests\test_control_center_full_monitor_run.py -q` | PASS, `10 passed in 5.83s` |
| `.venv\Scripts\python.exe -m pytest tests\test_control_center_actions.py tests\test_control_center_read_only_apis.py tests\test_control_center_truth_contract.py tests\test_control_center_route.py -q` | PASS, `24 passed in 12.76s` |
| `.venv\Scripts\python.exe -m py_compile ...changed python files...` | PASS |
| `npm test -- --run src/pages/fullMonitorRun.test.tsx` | PASS, `1 file`, `4 tests` |
| `npm test -- --run src/pages/controlActions.test.tsx` | PASS, `1 file`, `6 tests` |
| `npm test` | PASS, `12 files`, `74 tests` |
| `npm run typecheck` | PASS |
| `npm run build` | PASS, with existing chunk-size warning; app JS `539.35 kB` |
| `npm audit --audit-level=high` | PASS; 3 moderate Storybook/uuid advisories remain |
| `npm ls --depth=0` | PASS |
| Source scans | PASS with expected guard/denial text only |
| `git status --short` | UNAVAILABLE, not a Git worktree |

## 11. Safety Checklist

| Check | YES / NO / UNKNOWN | Notes |
| --- | --- | --- |
| actor required | YES | Start and stop reject missing actor. |
| reason required | YES | Start and stop reject missing reason. |
| duration required for start | YES | Missing duration returns `REJECTED` envelope. |
| audit id for accepted actions | YES | Start/stop include generated in-process audit ids. |
| State Governor checked | YES | Start checks current mode/permissions. |
| KILL blocks start | YES | KILL mode or kill switch returns `LOCKED`. |
| run bounded | YES | Synchronous one-pass default; `max_cycles` bounded 1..10. |
| stop safe | YES | Safe no-op when no active run exists; no destructive service/DB action. |
| unsafe modules skipped | YES | orderbook/news/whale/social/paper execution/live execution skipped. |
| no manual trade | YES | No manual trade UI/API added. |
| no override blocker | YES | No override blocker UI/API added. |
| no disable risk | YES | No disable risk UI/API added. |
| no disable governance | YES | No disable governance UI/API added. |
| no live trading | YES | Live execution is not called; live-order permission locks start. |
| no engine budget editing | YES | No budget editing added. |
| no raw dangerous route exposed | YES | Frontend posts only to Control Center action wrapper. |
| no DB destructive action | YES | No destructive DB action or migration. |
| no live orders/fills/positions created | YES | No execution services called. |
| read-only pages preserved | YES | Read-only regressions passed. |
| Stage 15 actions preserved | YES | Stage 15 action tests passed after expected start activation update. |
| frontend tests passed | YES | 74/74 passed. |
| backend tests passed | YES | 34/34 relevant backend tests passed. |
| build/typecheck/audit passed | YES | Build/typecheck passed; high audit passed. |

## 12. Remaining Risks

| Risk | Severity | Notes |
| --- | --- | --- |
| In-process run ledger | MEDIUM | Current/latest run state and audit id are memory-only. This avoids migration but is not durable across process restart. |
| Synchronous one-pass run | MEDIUM | Stage 16 proves safe start/stop contract, not a background long-running monitor loop. |
| Skipped modules | MEDIUM | orderbook/news/whale/social are skipped until safe Control Center read-only monitor endpoints are certified. |
| Paper execution skipped | MEDIUM | Paper execution can create paper orders/fills, so Stage 16 does not call it. |
| Moderate npm advisories | MEDIUM | Same Storybook/uuid chain as previous stages; high audit passes. |
| Bundle warning | LOW | Existing Vite chunk warning remains. |
| Git unavailable | LOW | Workspace is not a Git worktree. |

## 13. Phase Status

GREEN

## 14. Can Continue to Stage 17, Testing?

YES, after ChatGPT review accepts Stage 16.

Recommended Stage 17 focus: broader testing/visual QA, optional durable run ledger design review, and certification of any additional module-specific read-only monitor endpoints before turning skipped modules active.
