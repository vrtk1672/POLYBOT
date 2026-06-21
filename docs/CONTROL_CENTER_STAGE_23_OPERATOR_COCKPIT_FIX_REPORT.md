# POLYBOT Control Center V1.5 - Stage 23 Operator Cockpit Fix Report

## 1. Summary

Stage 23 fixed the Operator Cockpit visibility issues found in the Stage 22 browser audit and reran a browser-based Playwright audit against the Docker-served Control Center at `http://127.0.0.1:8000/control-center`.

Result: YELLOW / safe to proceed to the next UI audit phase.

The cockpit is materially clearer, the browser audit has zero console errors, zero network failures, and zero wrong-base-url requests. Full Monitor Run remains PARTIAL because the backend accepts the audited action request but the system truthfully locks the run by current mode instead of showing a real started run.

## 2. Dispatch Classification

- Executor: Codex
- Task mode: CONTROLLED_FRONTEND_PRODUCT_FIX_WITH_BROWSER_VERIFICATION
- Risk: MEDIUM
- ChatGPT review: YES
- Backend/API review: not required; no backend API or runtime logic was changed

## 3. Scope

Implemented frontend-only UX fixes for the Stage 21 Operator Cockpit and Stage 22 audit findings.

No backend APIs, trading logic, risk logic, execution logic, capital logic, migrations, or Docker configuration were changed.

## 4. Context Read

Read project and safety context including `AGENTS.md`, `README.md`, safety/workflow docs, context index, dispatch protocol, and the Stage 20, Stage 21, and Stage 22 Control Center reports.

`docs/POLYBOT_CODEX_PROMPT_STANDARD.md` was not present.

## 5. Files Changed

- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `frontend/control-center/src/pages/commandCenterRecovery.test.tsx`
- `frontend/control-center/src/pages/moneyVisibility.tsx`
- `frontend/control-center/src/components/truth/StatusCard.tsx`
- `run_reports/control_center_ui_audit/audit-control-center.mjs`
- `docs/CONTROL_CENTER_STAGE_23_OPERATOR_COCKPIT_FIX_REPORT.md`

Previously added Playwright dependency files remain part of the working tree from Stage 22 setup:

- `frontend/control-center/package.json`
- `frontend/control-center/package-lock.json`

## 6. Dependencies Added

No new dependency was added during this Stage 23 fix pass.

The existing Stage 22 setup added `@playwright/test` as a dev dependency in `frontend/control-center`.

## 7. Backend Changes

None.

## 8. Migrations

None.

## 9. Trading / Risk / Execution / Capital Changes

None.

No live, paper, shadow, order, fill, position, or migration command was run.

## 10. Operator Cockpit Changes

The Command Cockpit was reshaped into a clearer first screen:

- Body state: POLYBOT status, backend, database, system mode, and health verdict.
- Primary Action Strip: SYSTEM ON, SYSTEM OFF, START FULL MONITOR RUN, STOP CURRENT RUN, REFRESH, EXPORT REPORT, and isolated KILL SWITCH.
- Current Run / Action Guidance: explicit state-machine guidance.
- Live Brain Feed: readable event summaries instead of raw-only lines.
- Brain Dialogue Preview: real mesh dialogue events only.
- Decision / Blockers: no-trade and blocker truth surfaced.
- Money Verdict: ledger and positions truth without invented PnL.
- Attention / Problems: warnings, errors, and safety boundary.
- Advanced Diagnostics: raw source coverage de-emphasized but still available.

## 11. Full Monitor Run Behavior

The Full Monitor Run action remains truth-first:

- The button requires actor and reason before it enables.
- The browser audit successfully clicked `START FULL MONITOR RUN`.
- The request posted to `/dashboard/api/v2/control/actions/start-full-monitor-run`.
- The backend returned HTTP 200.
- The UI displayed `Locked` with the State Governor reason.
- No fake running state was shown.

Final audit status for this flow: PARTIAL.

## 12. Live Feed Result

The Live Brain Feed now shows readable runtime motion such as:

- Runtime cycle finished
- Runtime cycle started
- Technical event is visible; no readable summary was supplied

The audit found polling indicators and recent timestamps before and after the Full Monitor Run attempt.

## 13. Mesh Dialogue Result

The cockpit now previews real mesh dialogue events from the backend data path.

Final audit:

- Mesh dialogue heading present.
- Dialogue role/event lines present.
- `fakeDialogueDetected`: false.

## 14. Money Truth Result

Money panels continue to use ledger and positions envelopes only.

Operator-facing wording was normalized from `fake PnL` to `invented PnL` in shared Truth state and Money warning presentation.

Final artifact scan found no `fake PnL` phrase in Stage 23 raw artifacts or snapshots.

## 15. Browser Audit Artifacts

Artifacts were written to:

- `run_reports/control_center_ui_audit_stage23/raw/`
- `run_reports/control_center_ui_audit_stage23/screenshots/`
- `run_reports/control_center_ui_audit_stage23/snapshots/`
- `run_reports/control_center_ui_audit_stage23/traces/`

Key files:

- `run_reports/control_center_ui_audit_stage23/raw/audit-summary.json`
- `run_reports/control_center_ui_audit_stage23/raw/full-monitor-run-flow.json`
- `run_reports/control_center_ui_audit_stage23/raw/live-feed-analysis.json`
- `run_reports/control_center_ui_audit_stage23/raw/neural-dialogue-analysis.json`
- `run_reports/control_center_ui_audit_stage23/traces/control-center-ui-audit.zip`

Screenshots captured: 17.

## 16. Final Browser Audit Summary

Generated at: `2026-06-08T21:02:43.877Z`

- URL: `http://127.0.0.1:8000/control-center`
- Page count: 15
- Console errors: 0
- Network failures: 0
- Wrong base URL requests: 0
- Full Monitor Run flow: PARTIAL

## 17. Docker / Runtime Verification

Docker API service:

- `polybot_api` healthy
- Port `8000` owned by Docker API container

Endpoint checks:

- `/control-center`: HTTP 200
- `/dashboard/api/v2/control/overview`: JSON returned, status `PARTIAL`, truth_state `REFRESH_REQUIRED`
- `/dashboard/api/v2/control/full-monitor-run`: JSON returned, status `MISSING`, truth_state `UNKNOWN`

## 18. Tests Run

Frontend:

- `npm test`
- `npm run typecheck`
- `npm run build`

Docker/runtime:

- `docker compose build api`
- `docker compose up -d api`
- `docker compose ps api`
- `Invoke-WebRequest http://127.0.0.1:8000/control-center`
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/overview`
- `Invoke-RestMethod http://127.0.0.1:8000/dashboard/api/v2/control/full-monitor-run`

Browser:

- `node run_reports/control_center_ui_audit/audit-control-center.mjs` with `CONTROL_CENTER_AUDIT_DIR=run_reports/control_center_ui_audit_stage23`

## 19. Test Results

- Frontend tests: 14 passed, 82 tests passed
- Typecheck: passed
- Production build: passed
- Docker API health: healthy
- `/control-center`: 200
- Overview API: JSON returned
- Full Monitor Run API: JSON returned
- Playwright audit: completed

Build warning:

- Vite reports one chunk larger than 500 kB after minification. This is not new functional breakage and was not addressed in this phase.

## 20. Problems Found

One real residual issue remains:

- Full Monitor Run is still not a complete started-run UX flow. The backend accepts the action request with HTTP 200, but the State Governor locks monitoring/data collection in the current mode. The UI now explains this truthfully.

This is not a frontend crash and not fake success. It should be handled in a later backend/runtime/governance phase if product intent requires a true monitor-run start in this mode.

## 21. Safety Review

No unsafe controls were added.

The cockpit still does not expose:

- manual trade
- approve trade
- override blocker
- disable risk
- disable governance
- raw runtime endpoint
- order creation
- fill creation
- position creation

KILL remains confirmation-gated.

## 22. Status

Status: YELLOW.

Reason: All browser, network, Docker, endpoint, build, and frontend tests pass, but Full Monitor Run remains intentionally PARTIAL due to current runtime/governor truth.

## 23. Complete

- Operator Cockpit clarity fixes
- Truthful locked Full Monitor Run guidance
- Real mesh dialogue preview
- Readable live feed summaries
- Money wording cleanup
- Browser audit script Stage 23 output support
- Stage 23 Playwright artifacts
- Docker-served verification
- Stage 23 report

## 24. Safe To Proceed

Yes, safe to proceed to the next browser audit or review phase.

Do not claim Full Monitor Run as GREEN until the backend/runtime/governor path can start and expose a real run state.
