# POLYBOT Control Center V1.5 Stage 15 Control Actions Report

Date: 2026-06-08

## 1. Short Summary

Stage 15 is GREEN.

Implemented a strictly scoped Control Center action wrapper layer plus a gated Settings controls panel. The new backend action surface is limited to `POST /dashboard/api/v2/control/actions/{action_name}` and returns a typed action envelope. Active actions are `SYSTEM ON`, `SYSTEM OFF`, and `KILL SWITCH`; unsafe or unsupported actions are shown honestly as `LOCKED` or `NOT_IMPLEMENTED`.

No trading controls, manual trade buttons, risk override buttons, live controls, order/fill/position creation paths, DB migrations, or trading algorithm changes were added.

## 2. Current Reality Found

| Area | Reality |
| --- | --- |
| Existing runtime routes | `/runtime/mode/request`, `/runtime/kill`, and `/runtime/resume` exist, but these raw routes are not exposed to the frontend. |
| Existing system power routes | `/system/power/on` and `/system/power/off` exist, but these raw routes are not exposed to the frontend. |
| Existing audit capability | `system_power_transitions` and `system_state_history` are used by existing services. |
| Existing State Governor | `StateGovernor` exists and enforces mode permissions / KILL transitions. |
| Existing system power service | `SystemPowerService` requires actor/reason, writes transition audit, writes state history, and reports live disabled / no order creation. |
| Existing run orchestration | No safe bounded full-monitor-run start/stop contract was found for Control Center use. |
| Existing paper balance reset | No safe paper-only reset contract with audit persistence and ledger preservation was found. |
| Actions active | `system-on`, `system-off`, `kill-switch`. |
| Actions locked/not implemented | `start-full-monitor-run`, `stop-current-run`, `reset-paper-balance`. |
| Frontend action path | Settings page only; POSTs only to `/dashboard/api/v2/control/actions/{action_name}`. |
| Deviations | Export report was implemented frontend-only from loaded TanStack Query cache because no safe read-only backend export endpoint was found. |

## 3. Files Created

| File |
| --- |
| `app/control_center/action_contract.py` |
| `app/control_center/action_service.py` |
| `tests/test_control_center_actions.py` |
| `frontend/control-center/src/api/controlCenterActions.ts` |
| `frontend/control-center/src/api/useControlCenterActions.ts` |
| `frontend/control-center/src/pages/ControlActionsPanel.tsx` |
| `frontend/control-center/src/pages/controlActions.test.tsx` |
| `docs/CONTROL_CENTER_STAGE_15_CONTROL_ACTIONS_REPORT.md` |

## 4. Files Changed

| File | Change |
| --- | --- |
| `app/api/routes.py` | Added safe Control Center action wrapper endpoint. |
| `app/control_center/__init__.py` | Exported action contract/service types. |
| `frontend/control-center/src/pages/SettingsShell.tsx` | Replaced locked placeholder with Stage 15 controls panel. |
| `frontend/control-center/src/pages/index.ts` | Exported controls panel. |
| `frontend/control-center/src/pages/pageRegistry.ts` | Updated Settings page reality and safety notes. |
| `frontend/control-center/src/layout/TopSystemBar.tsx` | Updated copy for gated actions and visibility/action API split. |
| `frontend/control-center/src/layout/EndpointSourceHint.tsx` | Added Stage 15 action-wrapper copy when Settings points at the action endpoint prefix. |
| `frontend/control-center/src/pages/PageShell.tsx` | Clarified visibility pages remain GET-only. |
| `frontend/control-center/src/layout/shell.test.tsx` | Updated Stage 15 Settings safety assertions. |
| `frontend/control-center/src/pages/moneyVisibility.test.tsx` | Updated read-only visibility safety copy assertion. |

## 5. Files Deleted

None.

## 6. Actions Matrix

| Action | UI State | Backend Endpoint | Requires Actor/Reason | Requires Confirmation | Audit | State Governor Check | Result |
| ------ | -------- | ---------------- | --------------------- | --------------------- | ----- | -------------------- | ------ |
| REFRESH | available | none, frontend `invalidateQueries` only | NO | NO | NO | NO | Active read-only refresh. |
| EXPORT REPORT | available | none, frontend JSON snapshot only | NO | NO | NO | NO | Active read-only export. |
| SYSTEM ON | available | `POST /dashboard/api/v2/control/actions/system-on` | YES | NO | YES, `system_power_transitions` / `system_state_history` | YES | Active if DB/governor available and live setting is disabled; otherwise `LOCKED`. |
| SYSTEM OFF | available | `POST /dashboard/api/v2/control/actions/system-off` | YES | NO | YES, `system_power_transitions` / `system_state_history` | YES | Active if DB/governor available and live setting is disabled; otherwise `LOCKED`. |
| START FULL MONITOR RUN | not implemented | `POST /dashboard/api/v2/control/actions/start-full-monitor-run` | YES | NO | NO accepted audit | YES for wrapper validation only | `NOT_IMPLEMENTED`; safe bounded run contract missing. |
| STOP CURRENT RUN | not implemented | `POST /dashboard/api/v2/control/actions/stop-current-run` | YES | NO | NO accepted audit | YES for wrapper validation only | `NOT_IMPLEMENTED`; safe stop contract missing. |
| KILL SWITCH | available | `POST /dashboard/api/v2/control/actions/kill-switch` | YES | YES, `KILL` | YES, `system_state_history:{correlation_id}` | YES | Active through `StateGovernor.activate_kill`. |
| RESET PAPER BALANCE | locked | `POST /dashboard/api/v2/control/actions/reset-paper-balance` | YES | YES, `RESET PAPER BALANCE` | NO accepted audit | YES for wrapper validation only | `LOCKED`; safe paper-only reset contract missing. |

## 7. APIs Added

| Method | Endpoint | Purpose | Safety |
| ------ | -------- | ------- | ------ |
| POST | `/dashboard/api/v2/control/actions/{action_name}` | Safe Control Center action wrapper for approved action names. | Requires actor/reason, confirmation where needed, returns action envelope, routes active actions through existing safe services, and returns `LOCKED`/`NOT_IMPLEMENTED` instead of fake success. |

No raw runtime, system-power, risk, execution, paper, shadow, live, manual trade, override, or budget-edit endpoints were added to the frontend.

## 8. Tests Added

| Test File | Coverage |
| --- | --- |
| `tests/test_control_center_actions.py` | Action envelope shape, actor/reason rejection, accepted system power audit id, KILL confirmation, KILL State Governor audit, reset paper balance locked, wrapper endpoint rejection. |
| `frontend/control-center/src/pages/controlActions.test.tsx` | Allowed action set, no forbidden trading controls, actor/reason gate, KILL confirmation gate, locked/not implemented display, wrapper-only POST, audit/safety result display, frontend-only export. |

## 9. Tests Run and Exact Results

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m py_compile app\control_center\action_contract.py app\control_center\action_service.py app\api\routes.py tests\test_control_center_actions.py` | PASS |
| `.venv\Scripts\python.exe -m pytest tests\test_control_center_actions.py -q` | PASS, `7 passed in 5.28s` |
| `.venv\Scripts\python.exe -m pytest tests\test_control_center_read_only_apis.py tests\test_control_center_truth_contract.py tests\test_control_center_route.py -q` | PASS, `17 passed in 11.05s` |
| `npm test -- --run src/pages/controlActions.test.tsx` | PASS, `1 passed`, `6 tests passed` |
| `npm test` | PASS, `11 passed`, `70 tests passed` |
| `npm run typecheck` | PASS |
| `npm test -- --run src/pages/controlActions.test.tsx src/layout/shell.test.tsx` | PASS after final action-wrapper copy update, `2 passed`, `14 tests passed` |
| `npm run build` | PASS, with existing chunk-size warning; final app JS `537.09 kB` |
| `npm audit --audit-level=high` | PASS, no high/critical findings; 3 moderate Storybook/uuid advisories remain |
| `npm ls --depth=0` | PASS |
| `git status --short` | UNAVAILABLE, `fatal: not a git repository (or any of the parent directories): .git` |

## 10. Safety Checklist

| Check | YES / NO / UNKNOWN | Notes |
| --- | --- | --- |
| actor required | YES | Backend rejects missing actor for all known actions. |
| reason required | YES | Backend rejects missing reason for all known actions. |
| audit required for accepted actions | YES | Accepted system power and KILL actions include audit id. |
| State Governor checked | YES | Active actions load governor state/permissions; KILL routes through State Governor. |
| unsafe actions locked | YES | Reset paper balance locked; monitor run actions not implemented. |
| no manual trade | YES | No manual trade UI/API added. |
| no override blocker | YES | No override blocker UI/API added. |
| no disable risk | YES | No disable risk UI/API added. |
| no disable governance | YES | No disable governance UI/API added. |
| no live trading | YES | No live action added; system power locks if live flag is true. |
| no engine budget editing | YES | No budget editing UI/API added. |
| no raw dangerous route exposed | YES | Frontend posts only to `/dashboard/api/v2/control/actions/*`. |
| no DB destructive action | YES | No destructive DB operation added. |
| no orders/fills/positions created | YES | Action service does not call execution, order, fill, or position services. |
| no paper/shadow/live activated | YES | No mode activation to paper/shadow/live and no execution action added. |
| no fake success | YES | Unsafe actions return `LOCKED`/`NOT_IMPLEMENTED`; failures normalize to `ERROR`/`REJECTED`. |
| read-only pages preserved | YES | Read-only backend and frontend regressions passed. |
| frontend tests passed | YES | 70/70 passed. |
| backend tests passed | YES | 24/24 relevant backend tests passed. |
| build/typecheck/audit passed | YES | Build/typecheck passed; audit high passed with moderate residual advisories. |

## 11. Remaining Risks

| Risk | Severity | Notes |
| --- | --- | --- |
| ChatGPT review pending | MEDIUM | Required by prompt before proceeding. |
| Raw legacy/backend runtime routes still exist | MEDIUM | They were not removed and are not exposed by the frontend. The Control Center uses only the new wrapper. |
| System power actions depend on DB/governor availability | MEDIUM | If unavailable, the wrapper returns `LOCKED`; no fake success. |
| START/STOP monitor run unavailable | MEDIUM | No safe bounded orchestration contract found. |
| RESET PAPER BALANCE unavailable | MEDIUM | No safe paper-only reset contract with audit and ledger preservation found. |
| Moderate npm audit advisories | MEDIUM | Same Storybook/uuid advisory chain as Stage 14; high audit passes. |
| Bundle size warning | LOW | Existing React Flow/app bundle warning remains. |
| Git unavailable | LOW | Workspace is not a Git worktree, so diff cannot be verified with git. |

## 12. Phase Status

GREEN

## 13. Can Continue to Stage 16, Full Monitor Run?

YES, after ChatGPT review accepts this Stage 15 result.

Stage 16 should define a separate safe bounded full-monitor-run backend contract before enabling the currently `NOT_IMPLEMENTED` monitor run actions.
