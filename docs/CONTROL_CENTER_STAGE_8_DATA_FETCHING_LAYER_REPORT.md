# Control Center Stage 8 Data Fetching Layer Report

Date: 2026-06-08

## Purpose

Stage 8 connects the Stage 7 Control Center frontend shell to the Stage 5 read-only Control Center APIs through a frontend-only data fetching layer.

This phase adds a GET-only API client, canonical endpoint map, TanStack Query provider/hooks, central refresh policy, Zod Truth Contract validation, safe error normalization, manual refresh, and page-level rendering of backend Truth Contract envelopes.

No backend, runtime, database, trading, paper, shadow, live, risk, execution, exit, capital, or state-governor behavior was changed.

## Dispatch Classification

- Recommended executor: Claude Code
- Task mode: CONTROLLED_FEATURE
- Risk level: LOW to MEDIUM
- Codex review needed: YES only if backend/routing/runtime/state/risk/execution/exit/capital/paper/shadow/live/DB/migrations touched
- ChatGPT review needed: YES
- Reason: isolated frontend read-only API client and query hooks with no backend/runtime/trading changes.

## Current Reality Found

- `frontend/control-center` package existed from Stage 6.
- Stage 7 shell existed with sidebar, top system bar, page shells, and placeholder states.
- `@tanstack/react-query` was not installed before Stage 8.
- No `src/api` folder existed before Stage 8.
- No API client existed before Stage 8.
- No live fetch logic existed before Stage 8.
- `App.tsx` had no `QueryClientProvider` before Stage 8.
- Stage 6 `TruthEnvelopeSchema` existed and was reused for Zod validation.
- Stage 6 Truth Components existed and were reused for fetched envelopes.
- Stage 7 pages used shell/static placeholder envelopes before Stage 8.
- Stage 5 read-only backend endpoints were documented in `docs/CONTROL_CENTER_STAGE_5_READ_ONLY_APIS_REPORT.md`.
- `docs/POLYBOT_UI_DEVELOPMENT_PLAN.md` was not found.
- `docs/POLYBOT_CODEX_PROMPT_STANDARD.md` was not found.
- `docs/POLYBOT_AGENT_OUTPUT_REVIEW_STANDARD.md` was not found.

## Files Created

- `frontend/control-center/src/api/controlCenterEndpoints.ts`
- `frontend/control-center/src/api/controlCenterClient.ts`
- `frontend/control-center/src/api/queryClient.tsx`
- `frontend/control-center/src/api/refreshPolicy.ts`
- `frontend/control-center/src/api/useControlCenterQueries.ts`
- `frontend/control-center/src/api/controlCenterClient.test.ts`
- `frontend/control-center/src/api/useControlCenterQueries.test.tsx`
- `docs/CONTROL_CENTER_STAGE_8_DATA_FETCHING_LAYER_REPORT.md`

Generated/updated by package install/build:

- `frontend/control-center/package-lock.json`
- `frontend/control-center/node_modules/`
- `frontend/control-center/dist/`
- TypeScript build info files under `frontend/control-center/`

## Files Changed

- `frontend/control-center/package.json`
  - Added `@tanstack/react-query`.
- `frontend/control-center/src/App.tsx`
  - Wrapped shell in `ControlCenterQueryProvider`.
- `frontend/control-center/src/pages/pageRegistry.ts`
  - Added `endpointKey` values backed by the central endpoint map.
- `frontend/control-center/src/pages/PageShell.tsx`
  - Connected page shells to read-only query hooks.
  - Added fetched envelope rendering, safe loading envelope, query error envelope, and manual refresh.
- `frontend/control-center/src/layout/PageHeader.tsx`
  - Added optional read-only refresh button.
- `frontend/control-center/src/layout/TopSystemBar.tsx`
  - Updated labels to `READ_ONLY_API_LAYER` and `GET_ONLY_CONTROL_APIS`.
- `frontend/control-center/src/layout/Sidebar.tsx`
  - Updated copy to say no runtime actions.
- `frontend/control-center/src/layout/EndpointSourceHint.tsx`
  - Updated endpoint hint to Stage 8 GET-only fetching.
- `frontend/control-center/src/layout/shell.test.tsx`
  - Added fetch mocking and updated assertions for fetched read-only envelopes.

## Files Deleted

None.

## Dependencies Added

| Dependency | Purpose | Free/Open-source? | Notes |
| ---------- | ------- | ----------------- | ----- |
| `@tanstack/react-query@5.101.0` | Read-only frontend query cache, polling, loading state, and manual refetch | YES | Only TanStack package added; no Table, Router, Charts, Flow, Storybook, or Playwright added. |

## API Client / Endpoint Map

| Endpoint Key | Path | Polling Policy | Notes |
| ------------ | ---- | -------------- | ----- |
| `overview` | `/dashboard/api/v2/control/overview` | 10000 ms | Stage 5 read-only |
| `organs` | `/dashboard/api/v2/control/organs` | 10000 ms | Stage 5 read-only |
| `liveFlow` | `/dashboard/api/v2/control/live-flow` | 5000 ms | Stage 5 read-only |
| `decisionXray` | `/dashboard/api/v2/control/decision-xray` | 10000 ms | Stage 5 read-only |
| `blockers` | `/dashboard/api/v2/control/blockers` | 10000 ms | Stage 5 read-only |
| `closestActionable` | `/dashboard/api/v2/control/closest-actionable` | 10000 ms | Stage 5 read-only |
| `truthState` | `/dashboard/api/v2/control/truth-state` | 15000 ms | Stage 5 read-only |
| `riskEvidence` | `/dashboard/api/v2/control/risk-evidence` | 15000 ms | Stage 5 read-only |
| `lifecycleGovernance` | `/dashboard/api/v2/control/lifecycle-governance` | 15000 ms | Stage 5 read-only |
| `meshDialogues` | `/dashboard/api/v2/control/mesh-dialogues` | 15000 ms | Stage 5 read-only, hook exists for future page use |
| `pnlLedger` | `/dashboard/api/v2/control/pnl-ledger` | 30000 ms | Stage 5 read-only |
| `positions` | `/dashboard/api/v2/control/positions` | 15000 ms | Stage 5 read-only |
| `noTrade` | `/dashboard/api/v2/control/no-trade` | 30000 ms | Stage 5 read-only, hook exists for future page use |
| `ai` | `/dashboard/api/v2/control/ai` | 30000 ms | Stage 5 read-only |
| `logs` | `/dashboard/api/v2/control/logs` | 15000 ms | Stage 5 read-only |
| `truthContract` | `/dashboard/api/v2/control/truth-contract` | manual / no polling | Contract endpoint |

## Query Hooks Created

| Hook | Endpoint | Refresh Policy | Notes |
| ---- | -------- | -------------- | ----- |
| `useOverviewQuery` | `overview` | 10000 ms | Read-only GET |
| `useOrgansQuery` | `organs` | 10000 ms | Read-only GET |
| `useLiveFlowQuery` | `liveFlow` | 5000 ms | Read-only GET |
| `useDecisionXrayQuery` | `decisionXray` | 10000 ms | Read-only GET |
| `useBlockersQuery` | `blockers` | 10000 ms | Read-only GET |
| `useClosestActionableQuery` | `closestActionable` | 10000 ms | Read-only GET |
| `useTruthStateQuery` | `truthState` | 15000 ms | Read-only GET |
| `useRiskEvidenceQuery` | `riskEvidence` | 15000 ms | Read-only GET |
| `useLifecycleGovernanceQuery` | `lifecycleGovernance` | 15000 ms | Read-only GET |
| `useMeshDialoguesQuery` | `meshDialogues` | 15000 ms | Read-only GET |
| `usePnlLedgerQuery` | `pnlLedger` | 30000 ms | Read-only GET |
| `usePositionsQuery` | `positions` | 15000 ms | Read-only GET |
| `useNoTradeQuery` | `noTrade` | 30000 ms | Read-only GET |
| `useAiQuery` | `ai` | 30000 ms | Read-only GET |
| `useLogsQuery` | `logs` | 15000 ms | Read-only GET |
| `useTruthContractQuery` | `truthContract` | manual / no polling | Read-only GET |
| `useOptionalControlCenterQuery` | page-specific or none | endpoint policy or disabled | Used by Stage 8 page shells |

## Validation / Error Handling

- Zod validation uses the Stage 6 `TruthEnvelopeSchema`.
- All endpoint responses must parse as `status`, `source`, `last_updated`, `stale_after_seconds`, `truth_state`, `data`, `warnings`, and `errors`.
- Invalid Truth Contract responses become safe `ERROR` envelopes with `source: "frontend:zod_validation"` and `truth_state: "UNKNOWN"`.
- Invalid JSON becomes a safe `ERROR` envelope with `source: "frontend:json"`.
- Non-OK HTTP responses become safe `ERROR` envelopes with `source: "frontend:http"`.
- Network failures become safe `ERROR` envelopes with `source: "frontend:network"`.
- The client does not throw raw errors into UI components.
- `MISSING`, `PARTIAL`, `STALE`, and `NOT_IMPLEMENTED` are preserved as returned; the frontend does not upgrade them to `REAL`.
- Manual refresh is exposed as `Refresh read-only data` and calls only TanStack Query `refetch()`.
- Settings has no endpoint and does not get a refresh button.

## Tests Added

- `frontend/control-center/src/api/controlCenterClient.test.ts`
  - Endpoint map contains all Stage 5 endpoints plus truth-contract.
  - Refresh policy matches Stage 8 defaults.
  - Client sends `method: "GET"` only.
  - Client exposes no POST/PUT/PATCH/DELETE helpers.
  - Invalid Truth Contract response becomes `ERROR`.
  - Non-OK and network failures become `ERROR`.

- `frontend/control-center/src/api/useControlCenterQueries.test.tsx`
  - Query provider renders and creates a QueryClient.
  - Hooks preserve `MISSING`, `PARTIAL`, `STALE`, and `NOT_IMPLEMENTED`.
  - Hooks do not convert degraded states to `REAL`.
  - Pages render fetched backend status/source/warnings.
  - Manual refresh exists and does not expose forbidden controls.

Updated:

- `frontend/control-center/src/layout/shell.test.tsx`
  - Mocked read-only fetch responses for shell tests.
  - Updated top bar assertions for Stage 8 read-only API layer labels.
  - Preserved forbidden-control and fake-runtime-claim checks.

## Tests Run

Initial Stage 8 validation:

- `npm run test`
  - Result: FAILED once
  - Cause: test-only reused `Response` bodies and singleton query cache leakage between tests.
  - Fix: changed test fetch mocks to return fresh `Response` objects and made `ControlCenterQueryProvider` create a query client per mounted provider.

Final required verification:

- `npm run test`
  - Result: PASS
  - Test files: 5 passed
  - Tests: 30 passed

- `npm run build`
  - Result: PASS
  - Vite production build completed
  - Output included `dist/index.html`, CSS asset, JS asset

- `npm run typecheck`
  - Result: PASS
  - Command: `tsc --noEmit`

- `npm audit --json`
  - Result: PASS
  - Vulnerabilities: 0 total

- `npm ls @tanstack/react-query`
  - Result: PASS
  - Installed version: `@tanstack/react-query@5.101.0`

- `git status --short`
  - Result: NOT AVAILABLE
  - Reason: `fatal: not a git repository (or any of the parent directories): .git`

Additional source checks:

- POST/PUT/PATCH/DELETE method/helper scan: no matches.
- GET method confirmation: `frontend/control-center/src/api/controlCenterClient.ts:55`.
- Forbidden control label scan: matches only negative tests.

## Safety Checklist

| Check | Result |
| ----- | ------ |
| no backend API changed | YES |
| no DB writes | YES |
| no migrations | YES |
| no runtime started | YES |
| no paper/shadow/live activated | YES |
| no orders/fills/positions created | YES |
| no secrets printed | YES |
| only GET read-only APIs used | YES |
| no POST/PUT/PATCH/DELETE helper added | YES |
| no dangerous controls exposed | YES |
| no fake green introduced | YES |
| no fake PnL introduced | YES |
| no fake runtime status introduced | YES |
| invalid responses handled as ERROR | YES |
| MISSING/PARTIAL/STALE preserved honestly | YES |
| only approved dependency added | YES |
| no paid/pro/cloud-only/license-key package added | YES |
| frontend tests passed | YES |
| frontend build passed | YES |
| frontend typecheck passed | YES |
| npm audit passed | YES |

## Remaining Risks

- The isolated frontend package is still not wired into FastAPI `/control-center`; this remains a future integration step.
- Stage 8 shows compact envelope summaries and safe raw data previews, not final polished core visibility screens.
- If the backend is unavailable in a running browser, pages will honestly show frontend `ERROR` envelopes.
- Generated artifacts exist locally after install/build (`node_modules`, `dist`, TypeScript build info).
- Browser visual QA was not run because the task's allowed command list did not include starting a dev server.

## Rollback Notes

To roll back Stage 8:

- Remove `@tanstack/react-query` from `frontend/control-center/package.json`.
- Revert `frontend/control-center/package-lock.json`.
- Remove `frontend/control-center/src/api/`.
- Restore Stage 7 versions of `App.tsx`, `PageShell.tsx`, `pageRegistry.ts`, and the touched layout/test files.
- Remove `docs/CONTROL_CENTER_STAGE_8_DATA_FETCHING_LAYER_REPORT.md`.

No database rollback is needed.

## Definition Of Done

- Data fetching layer created: YES
- TanStack Query wired: YES
- Endpoint map created: YES
- Hooks created: YES
- Zod validation enforced: YES
- Invalid responses fail safely as `ERROR`: YES
- Only GET read-only APIs used: YES
- No dangerous controls: YES
- Tests passed: YES
- Build passed: YES
- Typecheck passed: YES
- Audit passed: YES

## Next Recommended Phase

Stage 9, Core Visibility Pages.

Recommended Stage 9 scope: build richer source-backed page bodies for Overview, Decision X-Ray, Blocker Center, Organ Health, PnL/Ledger, Positions, Logs, and related panels using the Stage 8 envelopes without adding mutating controls.

## Phase Status

GREEN.

## Can Continue To Stage 9, Core Visibility Pages?

YES.
