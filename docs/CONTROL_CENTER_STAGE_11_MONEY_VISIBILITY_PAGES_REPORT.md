# POLYBOT Control Center V1.5 - Stage 11 Money Visibility Pages Report

Date: 2026-06-08
Executor: Codex
Task mode: CONTROLLED_FEATURE
Risk: LOW to MEDIUM
ChatGPT review: REQUIRED by prompt
Codex review: Not required; no backend/API/runtime/trading changes were made.

## Summary

Stage 11 is complete for the frontend Control Center money visibility scope.

Implemented read-only visibility pages for:

- PnL & Ledger
- Capital
- Positions
- No-Trade

The implementation uses the existing Stage 5 read-only endpoint map and Stage 8 TanStack Query fetch layer. No backend APIs, routing, database code, runtime code, trading logic, capital logic, or execution logic were changed.

## Current Reality Found

- `frontend/control-center` already had a Vite/React/TanStack Query package with page shells, sidebar, top bar, Truth Components, endpoint map, Zod validation, and polling policy.
- Existing endpoint map already included:
  - `/dashboard/api/v2/control/pnl-ledger`
  - `/dashboard/api/v2/control/positions`
  - `/dashboard/api/v2/control/no-trade`
  - `/dashboard/api/v2/control/overview`
- Existing hooks already included:
  - `usePnlLedgerQuery`
  - `usePositionsQuery`
  - `useNoTradeQuery`
  - `useOverviewQuery`
- Refresh policy already covered:
  - `pnlLedger`: 30000 ms
  - `positions`: 15000 ms
  - `noTrade`: 30000 ms
  - `overview`: 10000 ms
- Before this stage:
  - PnL & Ledger and Positions used simple truth cards.
  - Capital was a generic overview-backed preview.
  - No-Trade had an endpoint and hook but no navigable page.
- Backend inspection confirmed:
  - PnL source is `paper_pnl_ledger`.
  - Positions source is `paper_positions`.
  - No-Trade source is `no_trade_log`.
  - No dedicated capital endpoint exists.
- Capital therefore uses `overview` only. If overview does not include a capital/capital reconciliation section, the page shows a missing/partial limitation instead of displaying balances.

## Files Created

- `frontend/control-center/src/pages/moneyVisibility.tsx`
- `frontend/control-center/src/pages/moneyVisibility.test.tsx`
- `frontend/control-center/src/pages/NoTradeShell.tsx`
- `docs/CONTROL_CENTER_STAGE_11_MONEY_VISIBILITY_PAGES_REPORT.md`

## Files Changed

- `frontend/control-center/src/App.tsx`
- `frontend/control-center/src/layout/Sidebar.tsx`
- `frontend/control-center/src/pages/PageShell.tsx`
- `frontend/control-center/src/pages/index.ts`
- `frontend/control-center/src/pages/pageRegistry.ts`

## Files Deleted

None.

## Page Implementations

| Page | Endpoint | Hook | What it shows | Truth behavior |
| --- | --- | --- | --- | --- |
| PnL & Ledger | `/dashboard/api/v2/control/pnl-ledger` | `usePnlLedgerQuery` through `useOptionalControlCenterQuery` | Ledger status, source, reconciliation, balances if supplied, realized/unrealized PnL, ledger rows, warnings/errors | Money values are withheld if source is missing or non-ledger. |
| Capital | `/dashboard/api/v2/control/overview` | `useOverviewQuery` through `useOptionalControlCenterQuery` | Overview-backed capital reconciliation only if overview contains a capital section | Shows missing/partial limitation when no capital section exists. No dedicated capital endpoint was invented. |
| Positions | `/dashboard/api/v2/control/positions` | `usePositionsQuery` through `useOptionalControlCenterQuery` | Canonical `paper_positions` rows, counts, source summary, warnings/errors | Orders and fills are not rendered as positions. Rows are withheld for non-canonical source. |
| No-Trade | `/dashboard/api/v2/control/no-trade` | `useNoTradeQuery` through `useOptionalControlCenterQuery` | No-trade source, first-class flag, latest no-trade records, top reasons, warnings/errors | Reasons are shown only from backend no-trade data; no frontend reason synthesis. |

## Tests Added

- `frontend/control-center/src/pages/moneyVisibility.test.tsx`

Coverage added:

- Ledger-backed PnL rendering.
- PnL withholding when source is missing/non-ledger.
- Capital overview-backed reconciliation rendering.
- Capital missing/partial state when overview lacks capital data.
- Canonical position rendering from `paper_positions`.
- Orders/fills not treated as positions.
- Backend-supplied no-trade records/reasons rendering.
- No-trade missing-source empty state.
- Money pages remain read-only and expose only manual refresh.

## Tests Run

From `frontend/control-center`:

- `npm test -- --run src/pages/moneyVisibility.test.tsx`
  - Result: PASS
  - Test files: 1 passed
  - Tests: 9 passed
- `npm run typecheck`
  - Result: PASS
  - `tsc --noEmit`
- `npm test`
  - Result: PASS
  - Test files: 8 passed
  - Tests: 51 passed
- `npm run build`
  - Result: PASS
  - `tsc -b && vite build`
  - Output included `dist/index.html`, CSS, and JS assets.
- `npm audit --audit-level=high`
  - Result: PASS
  - `found 0 vulnerabilities`
- `npm ls --depth=0`
  - Result: PASS
  - Dependency tree listed successfully.

Repo-level:

- `git status --short`
  - Result: NOT RUN SUCCESSFULLY
  - Reason: `fatal: not a git repository (or any of the parent directories): .git`

## Safety Checklist

- Backend APIs changed: NO
- FastAPI routing changed: NO
- Runtime/state governor touched: NO
- Risk/execution/exit/capital trading logic touched: NO
- Database or migrations touched: NO
- Mutating frontend APIs added: NO
- Live/paper/shadow order actions exposed: NO
- PnL displayed without ledger source: NO
- Positions invented from orders/fills: NO
- No-trade reasons invented by frontend: NO
- Capital endpoint invented: NO
- Capital limitation shown when source missing: YES
- Manual refresh remains GET-only: YES
- Source scans found forbidden mutating helpers: NO
- Git status available: NO

## Remaining Risks

- Capital visibility is limited by the current overview payload. Until a dedicated read-only capital endpoint or explicit overview capital section exists, Capital correctly remains partial/missing.
- The money pages render flexible backend payload shapes because Stage 5 envelopes can wrap service payloads with nested keys. If backend schemas become stricter, the page adapters can be tightened later.
- No browser visual QA was run in this stage; verification was via tests, typecheck, build, audit, dependency listing, and source scans.

## Phase Status

GREEN.

Stage 11 frontend money visibility pages are implemented and verified within the allowed scope.

## Safe To Proceed

YES.

Ready to continue to Stage 12 React Flow Decision Graph / next phase, subject to normal prompt review.
