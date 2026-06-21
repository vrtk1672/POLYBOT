# POLYBOT Control Center V1.5 - Stage 19 Live Integration Visual QA Report

Date: 2026-06-08

## 1. Short Summary

Stage 19 recovered the Control Center from a placeholder-served shell into a usable FastAPI-served React app at `/control-center`, with a first-screen Command Center that shows backend connection, source-backed body truth, monitor run truth, blockers, money truth, logs/errors, and safe action boundaries.

## 2. Current Reality Found

- `frontend/control-center` already had the Stage 8 GET-only API client, endpoint map, TanStack Query hooks, Zod validation, polling policy, and page shell infrastructure.
- Stage 9+ visibility pages existed and consumed hooks, but `/control-center` in FastAPI still served a placeholder when the running process had not been restarted.
- The active server on port 8000 was still serving the old placeholder during QA; the updated code serves the built app after restart.
- No backend API change was needed for visibility data.

## 3. Root Cause of Bad UX

The real frontend build existed, but FastAPI did not serve `frontend/control-center/dist` at `/control-center`. The Overview route also still felt like a generic shell instead of a command surface, and the navigation was too flat for an operator trying to answer whether the body is alive, stale, missing, degraded, or broken.

## 4. What Was Fixed

- Added safe static serving helpers for the built Control Center dist.
- Updated FastAPI `/control-center` to serve `dist/index.html`, static assets, and SPA fallback while preserving the placeholder fallback when dist is absent.
- Added Vite `base: "/control-center/"` and a dev proxy for `/dashboard/api`.
- Replaced Overview shell with a source-backed Command Center home.
- Added first-screen panels for backend connection, system power/mode, latest data, organs, full monitor run, source coverage, latest source rows, blockers, money truth, logs/errors, safe actions, and safety boundary.
- Reorganized sidebar into Primary and Advanced Truth sections.
- Added read-only refresh back to the first screen.
- Tightened UI copy so safety scans do not confuse visibility language for hidden controls.

## 5. Files Created

- `app/control_center/static_serving.py`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `docs/CONTROL_CENTER_STAGE_19_LIVE_INTEGRATION_VISUAL_QA_REPORT.md`

## 6. Files Changed

- `app/api/routes.py`
- `frontend/control-center/vite.config.ts`
- `frontend/control-center/src/pages/OverviewShell.tsx`
- `frontend/control-center/src/pages/pageRegistry.ts`
- `frontend/control-center/src/layout/Sidebar.tsx`
- `frontend/control-center/src/pages/decisionIntelligence.tsx`
- `tests/test_control_center_route.py`
- `tests/test_control_center_truth_contract.py`

## 7. APIs / Serving Changes

- Added serving only, not new data APIs.
- `GET /control-center` now serves the built React app when `frontend/control-center/dist/index.html` exists.
- `GET /control-center/{asset_path:path}` now serves built assets, returns 404 for missing assets, and falls back to SPA index for client routes.
- Existing Stage 5 read-only endpoints remain unchanged.
- Existing Stage 15 audited action wrapper remains unchanged.

## 8. UI / UX Changes

- Overview is now "Command Center" and functions as the operator's first real status screen.
- Navigation prioritizes Command Center, Decision X-Ray, PnL & Ledger, Logs & Errors, and Settings.
- Advanced visibility pages remain accessible under Advanced Truth.
- The UI makes missing/unknown states visible instead of turning them green.
- PnL values remain withheld unless the source is ledger-backed.
- Monitor-run and safe-action panels explain what exists without exposing direct trade controls.

## 9. Actions Still Safe

- Refresh read-only data: GET-only query invalidation.
- Export read-only snapshot: frontend-only export of loaded truth.
- Settings action buttons remain under the existing audited Control Center action wrapper.
- No manual trade, live order, risk bypass, budget editor, or raw runtime route was added.

## 10. Tests Added

- Frontend recovery test for the Command Center first screen.
- Backend route tests for serving built React index/static assets and preserving placeholder fallback.

## 11. Tests Run and Exact Results

- `.venv\Scripts\python.exe -m pytest tests\test_control_center_route.py tests\test_control_center_stage17_safety_certification.py -q` -> 10 passed.
- `$tests = Get-ChildItem -Path tests -Filter 'test_control_center_*.py' | ForEach-Object { $_.FullName }; .venv\Scripts\python.exe -m pytest @tests -q` -> 41 passed.
- `npm test -- --run src/pages/commandCenterRecovery.test.tsx src/pages/coreVisibility.test.tsx src/layout/shell.test.tsx` -> 13 passed.
- `npm test` -> 14 files passed, 81 tests passed.
- `npm run typecheck` -> passed.
- `npm run build` -> passed; Vite warned that one chunk is larger than 500 kB.
- `npm run storybook:build` -> passed; Storybook emitted expected eval/deprecation/chunk-size warnings.
- `npm audit --audit-level=high` -> exit 0; reports 3 moderate Storybook/uuid findings only.
- `npm ls --depth=0` -> passed.
- `.venv\Scripts\python.exe -m py_compile ...` for Control Center, routes, and main -> passed.

## 12. Source Scans

- Forbidden rendered/control vocabulary scan: only backend safety warning remains in `app/control_center/action_service.py` saying system power actions do not enable live trading and do not create execution artifacts.
- Fake success / fake PnL scan: no matches in frontend source.
- Live order / order artifact creation scan: no matches.
- Mutating method scan: frontend visibility client uses GET; existing `controlCenterActions.ts` uses POST only for the audited action wrapper.

## 13. Manual Run Instructions

1. Build frontend: `cd C:\Server\apps\polybot\frontend\control-center && npm run build`
2. Restart the FastAPI server so it loads the updated routes.
3. Open `http://127.0.0.1:8000/control-center`.
4. For Vite development: `cd C:\Server\apps\polybot\frontend\control-center && npm run dev`, then use the configured `/dashboard/api` proxy to the backend.

## 14. What the Operator Should See

- Sidebar with Primary and Advanced Truth groups.
- First screen named Command Center.
- Backend connection panel with Truth Contract status.
- Explicit endpoint labels for overview and full monitor run.
- Latest Data, Organs, Full Monitor Run, Operator Attention tiles.
- Body Truth, Latest Full Monitor Run, Source Coverage, Latest Source Rows, Blockers, Money Truth, Logs & Errors, Safe Actions, and Safety Boundary sections.

## 15. Known Remaining Issues

- The already-running server on port 8000 was still serving the old placeholder during QA and needs restart to pick up this code.
- Production bundle has a Vite chunk-size warning.
- `npm audit --audit-level=high` passes, but moderate Storybook/uuid advisories remain.
- Settings still uses the existing Stage 15 action wrapper; this phase did not redesign action certification.

## 16. Safety Checklist

- No live trading enabled.
- No trading logic touched.
- No DB or migration touched.
- No runtime mode/governor/risk/execution/capital/exit logic touched.
- No new backend data APIs added.
- No secrets exposed.
- Missing data stays missing.
- PnL remains ledger-only.
- Browser QA found no forbidden-control button text.

## 17. Phase Status

GREEN.

The code builds, tests pass, audit at high severity passes, source scans are clean for frontend visibility risks, and browser QA verified the built app through FastAPI serving on a safe temporary QA port.

## 18. Can Continue

YES.

## 19. Recommended Next Step

Restart the real FastAPI process, open `/control-center`, and then run the next stage against the live operator environment: focused polish on Settings action certification, clearer full-monitor-run history, and production bundle splitting.
