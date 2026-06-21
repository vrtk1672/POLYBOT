# POLYBOT Control Center V1.5 - Stage 21 Operator Cockpit Redesign Report

Date: 2026-06-08
Executor: Codex
Task Mode: CONTROLLED_FEATURE
Risk: LOW to MEDIUM
Backend API Changes: None
Trading Logic Changes: None

## 1. Short Summary

Stage 21 redesigned the Control Center first screen into an operator cockpit. The new cockpit brings system state, safe action controls, Full Monitor Run visibility, live feed visibility, mesh dialogue visibility, decision blockers, money truth, organ/source coverage, and protected boundaries into one page.

The implementation remains frontend-only and uses the existing Stage 5 read-only APIs, Stage 8 query hooks, and existing audited Control Center action wrapper.

## 2. UX Problem Found

The previous first screen was still too diagnostic and scattered for real operator use. Critical controls and body state existed, but the operator had to move through multiple pages to answer:

Is POLYBOT alive, stale, missing, degraded, or broken?

The Control Center also had too much advanced detail before the operator had a plain cockpit view.

## 3. What Was Redesigned

- Replaced the Overview first screen with `Command Cockpit`.
- Promoted primary navigation to: Command Cockpit, Decision, Money, Live, Controls.
- Moved advanced/detail pages below the primary operator path.
- Added cockpit sections:
  - System Power / Backend / Database / Runtime Mode
  - Operator Controls
  - Full Monitor Run
  - Live System Feed
  - Neural Dialogue
  - Decision Summary
  - Money Truth
  - System Organs
  - Needs Attention
  - Source Coverage / Latest Source Rows
  - Protected Boundary

## 4. Files Created

- `docs/CONTROL_CENTER_STAGE_21_OPERATOR_COCKPIT_REPORT.md`

## 5. Files Changed

- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/layout/Sidebar.tsx`
- `frontend/control-center/src/pages/pageRegistry.ts`
- `frontend/control-center/src/pages/ControlActionsPanel.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `frontend/control-center/src/layout/shell.test.tsx`
- `frontend/control-center/src/api/useControlCenterQueries.test.tsx`
- `frontend/control-center/src/pages/controlActions.test.tsx`
- `frontend/control-center/src/pages/coreVisibility.test.tsx`
- `frontend/control-center/src/pages/decisionGraph.test.tsx`
- `frontend/control-center/src/pages/decisionIntelligence.test.tsx`
- `frontend/control-center/src/pages/fullMonitorRun.test.tsx`
- `frontend/control-center/src/pages/moneyVisibility.test.tsx`
- `frontend/control-center/src/pages/stage17Safety.test.tsx`

## 6. Control Actions Visibility

Visible cockpit controls:

- SYSTEM ON
- SYSTEM OFF
- START FULL MONITOR RUN
- STOP CURRENT RUN
- KILL SWITCH
- REFRESH
- EXPORT REPORT

All backend actions still use only:

`/dashboard/api/v2/control/actions/{action_name}`

Required safety fields:

- actor
- reason
- duration for Full Monitor Run
- `KILL` confirmation for KILL SWITCH

Forbidden controls remain absent:

- manual trade
- approve trade
- override blocker
- disable risk
- disable governance
- engine budget
- direct order/fill/position creation

## 7. Full Monitor Run Visibility

The cockpit now shows the current or latest Full Monitor Run from `useFullMonitorRunQuery`.

Visible fields include:

- status
- run id
- duration
- cycles
- markets
- events
- no-trades
- opportunities
- warnings
- errors

When no process-local run exists, the cockpit explicitly says:

`No Full Monitor Run has been started in this process.`

## 8. Live Feed / Dialogue Handling

Live feed uses:

- `useLiveFlowQuery`
- `useLogsQuery`

Mesh dialogue uses:

- `useMeshDialoguesQuery`

If no live events or dialogue rows exist, the cockpit shows explicit empty states. It does not invent dialogue, events, or fake live activity.

## 9. Tests Added

The Stage 19 recovery test was upgraded into a Stage 21 Operator Cockpit contract test.

Existing shell, query, safety, action, full monitor run, decision, graph, money, and core visibility tests were updated to match the redesigned primary navigation labels while preserving prior safety assertions.

## 10. Tests Run and Exact Results

Targeted cockpit regression:

`npm test -- --run src/pages/commandCenterRecovery.test.tsx src/layout/shell.test.tsx`

Result:

- Test Files: 2 passed (2)
- Tests: 9 passed (9)

Targeted prior safety/visibility regression:

`npm test -- --run src/api/useControlCenterQueries.test.tsx src/pages/coreVisibility.test.tsx src/pages/fullMonitorRun.test.tsx src/pages/stage17Safety.test.tsx src/pages/controlActions.test.tsx src/pages/decisionIntelligence.test.tsx src/pages/decisionGraph.test.tsx src/pages/moneyVisibility.test.tsx`

Result:

- Test Files: 8 passed (8)
- Tests: 49 passed (49)

Full frontend test suite:

`npm test`

Result:

- Test Files: 14 passed (14)
- Tests: 81 passed (81)

Typecheck:

`npm run typecheck`

Result:

- Passed

Production build:

`npm run build`

Result:

- Passed
- Vite emitted a non-blocking chunk-size warning for `assets/index-yxujyOPy.js` at 564.06 kB.

## 11. Docker Rebuild Result

Command:

`docker compose build api`

Result:

- Passed
- New frontend `dist` was copied into the API image.

Command:

`docker compose up -d api`

Result:

- Passed
- `polybot_api` started.

Command:

`docker compose ps api`

Result:

- `polybot_api` healthy
- Port mapping: `0.0.0.0:8000->8000/tcp`

## 12. Browser Verification

Verified in the in-app browser at:

`http://localhost:8000/control-center`

Confirmed visible:

- Command Cockpit
- Operator Controls
- SYSTEM ON
- SYSTEM OFF
- START FULL MONITOR RUN
- STOP CURRENT RUN
- KILL SWITCH
- Full Monitor Run
- Live System Feed
- Neural Dialogue
- Money Truth
- Protected Boundary

Also verified the served Overview API:

`/dashboard/api/v2/control/overview`

Returned:

- `status`: `PARTIAL`
- `source`: `runtime_state_service_health_event_log`
- `truth_state`: `REFRESH_REQUIRED`
- DB-backed source counts
- `read_only`: `true`
- `mutating_actions_exposed`: `[]`

## 13. Safety Checklist

- No backend APIs added.
- No backend routing changed.
- No trading logic touched.
- No runtime, risk, execution, exit, capital, DB, or migration changes.
- No direct live controls exposed.
- No order placement exposed.
- No fill creation exposed.
- No position mutation exposed.
- No blocker override exposed.
- No fake green status added.
- No fake PnL added.
- PnL values are shown only from ledger payload fields.
- Missing or empty live/dialogue data remains explicit.

## 14. Remaining Issues

- The production JS bundle still exceeds Vite's default 500 kB warning threshold. This is pre-existing scale pressure and not a Stage 21 correctness blocker.
- Browser verification showed the live Docker page as data-truthful but currently degraded/partial, which is correct for the current runtime state.
- This workspace path did not expose a `.git` directory to `git status`; changed files were tracked from implementation scope and verification instead.

## 15. Phase Status

GREEN

Stage 21 is implemented as a frontend-only operator cockpit redesign with tests, build, Docker rebuild, and browser verification passing.

## 16. Can Continue

YES

Safe to continue to the next frontend Control Center phase. Backend/core runtime review is not required for this phase because no backend/runtime/trading code was changed.
