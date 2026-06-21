# POLYBOT Control Center V1.5 Stage 10 Build Report

Stage: Decision Intelligence Pages  
Date: 2026-06-08  
Executor: Claude Code  
Task mode: CONTROLLED_FEATURE  
Risk: MEDIUM  

## Dispatch Classification

- Recommended executor: Claude Code
- Task mode: CONTROLLED_FEATURE
- Risk level: MEDIUM
- Codex review needed: YES only if backend source is missing and cannot be represented honestly by existing Stage 5 APIs, or if backend/API changes are required
- ChatGPT review needed: YES

## Current Reality Found

- `frontend/control-center` already contains the Stage 7 shell, Stage 8 GET-only data layer, and Stage 9 core visibility pages.
- The Stage 8 endpoint map already includes all Stage 10 read-only paths:
  - `/dashboard/api/v2/control/decision-xray`
  - `/dashboard/api/v2/control/blockers`
  - `/dashboard/api/v2/control/closest-actionable`
  - `/dashboard/api/v2/control/truth-state`
  - `/dashboard/api/v2/control/risk-evidence`
  - `/dashboard/api/v2/control/lifecycle-governance`
  - `/dashboard/api/v2/control/mesh-dialogues`
- The Stage 8 hooks already exist:
  - `useDecisionXrayQuery`
  - `useBlockersQuery`
  - `useClosestActionableQuery`
  - `useTruthStateQuery`
  - `useRiskEvidenceQuery`
  - `useLifecycleGovernanceQuery`
  - `useMeshDialoguesQuery`
- `PageShell` already fetches by endpoint key through `useOptionalControlCenterQuery`.
- Before Stage 10, Decision X-Ray was a placeholder chain, Blocker Center and Risk Evidence Mesh used compact generic truth cards, Closest to Actionable / Truth State / Lifecycle Governance used generic safe previews, and Mesh Dialogues was not a visible page.
- Stage 5 backend endpoints already expose enough read-only Truth Contract data to build honest frontend visibility.
- No backend change was needed.

## Summary

Implemented Stage 10 Decision Intelligence frontend pages:

- Decision X-Ray
- Blocker Center
- Closest to Actionable
- Truth State
- Risk Evidence Mesh
- Lifecycle Governance
- Mesh Dialogues

The pages render existing Stage 5 read-only endpoint data through the Stage 8 query layer. They preserve degraded backend truth states, show warnings/errors, tolerate missing nested data, and expose no controls or mutating API paths.

## Files Created

- `frontend/control-center/src/pages/decisionIntelligence.tsx`
- `frontend/control-center/src/pages/decisionIntelligence.test.tsx`
- `frontend/control-center/src/pages/MeshDialoguesShell.tsx`
- `docs/CONTROL_CENTER_STAGE_10_DECISION_INTELLIGENCE_PAGES_REPORT.md`

## Files Changed

- `frontend/control-center/src/pages/PageShell.tsx`
- `frontend/control-center/src/pages/pageRegistry.ts`
- `frontend/control-center/src/pages/index.ts`
- `frontend/control-center/src/App.tsx`
- `frontend/control-center/src/layout/Sidebar.tsx`

## Files Deleted

None.

## Migrations

None.

## Backend/API Changes

None.

## Dependencies

No dependencies added.

## Page Implementations

| Page | Endpoint | Hook | What it shows | Truth behavior |
| ---- | -------- | ---- | ------------- | -------------- |
| Decision X-Ray | `/dashboard/api/v2/control/decision-xray` | `useDecisionXrayQuery` | Truth status, source, last update, decision evidence summary, blocked-by map, missing evidence, recent evidence rows, warnings/errors | Preserves backend status and never claims approval beyond backend data |
| Blocker Center | `/dashboard/api/v2/control/blockers` | `useBlockersQuery` | No-trade blockers, top blocker reasons, missing requirements, risk blocker subtypes, risk-source selection, Risk Review traces | Preserves `PARTIAL/MISSING/STALE`; no blocker invented |
| Closest to Actionable | `/dashboard/api/v2/control/closest-actionable` | `useClosestActionableQuery` | Candidates with id/market/actionability/truth_state/blockers; omits candidate rows missing `truth_state` | Does not show a candidate as actionable unless backend truth provides it |
| Truth State | `/dashboard/api/v2/control/truth-state` | `useTruthStateQuery` | `ACTIVE_FRESH`, `LAST_KNOWN`, `HISTORICAL_ONLY`, `REFRESH_REQUIRED`, `UNKNOWN`, source map, latest truth records | Shows freshness/staleness exactly from backend counts |
| Risk Evidence Mesh | `/dashboard/api/v2/control/risk-evidence` | `useRiskEvidenceQuery` | Risk source, risk decision counts, source-backed edge, critical blockers, optional evidence gaps, stale legacy risk ignored, latest evidence | Does not claim Risk Gate approval or safety |
| Lifecycle Governance | `/dashboard/api/v2/control/lifecycle-governance` | `useLifecycleGovernanceQuery` | Actionability classes, selected risk source/freshness, legacy risk ignored, kept-blocked/promoted/actionable counts, critical gates, allow-paper counts, latest decisions | Shows blocked/actionable counts only as backend summaries; no actions exposed |
| Mesh Dialogues | `/dashboard/api/v2/control/mesh-dialogues` | `useMeshDialoguesQuery` | Brain/dialogue events, source, message/opinion/confidence/status/conflicts/final summaries if present | Shows honest missing state when no events exist; no dialogue invented |

## Tests Added

- `frontend/control-center/src/pages/decisionIntelligence.test.tsx`
  - Decision X-Ray renders backend truth status/source/warnings/errors.
  - Blocker Center renders blockers and preserves `PARTIAL`.
  - Closest to Actionable renders only candidates with `truth_state`.
  - Truth State renders the required truth vocabulary.
  - Risk Evidence Mesh renders risk evidence and does not claim approval.
  - Lifecycle Governance renders actionability state and blockers.
  - Mesh Dialogues renders no invented dialogue when source is missing.
  - Manual refresh remains GET-only and no dangerous/fake controls appear.

## Tests Run And Exact Results

- `npm test -- --run src/pages/decisionIntelligence.test.tsx`
  - Result: PASS, 1 file passed, 8 tests passed.
- `npm test`
  - Result: PASS, 7 files passed, 42 tests passed.
- `npm run typecheck`
  - Result: PASS.
- `npm run build`
  - Result: PASS.
- `npm audit --audit-level=high`
  - Result: PASS, 0 vulnerabilities.
- `npm ls --depth=0`
  - Result: PASS.
- Forbidden non-test source scan:
  - Command: `rg -n "fake green|fake approval|fake pnl|fake runtime status|SYSTEM ON|SYSTEM OFF|START RUN|STOP RUN|KILL SWITCH|RESET BALANCE|send order|create order|live order|POST|PUT|PATCH|DELETE" frontend/control-center/src --glob "!*test*"`
  - Result: PASS, no matches.
- `git status --short`
  - Result: NOT AVAILABLE, `fatal: not a git repository (or any of the parent directories): .git`

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
| no fake approval introduced | YES |
| no fake PnL introduced | YES |
| no fake runtime status introduced | YES |
| no invented blockers | YES |
| no invented dialogue | YES |
| MISSING/PARTIAL/STALE preserved honestly | YES |
| frontend tests passed | YES |
| frontend build passed | YES |
| frontend typecheck passed | YES |
| npm audit passed | YES |

## Remaining Risks

- Backend `/control-center` frontend wiring remains outside this stage, as noted in prior stages.
- Browser visual QA was not performed because no dev server was started under the allowed command list.
- The UI is intentionally schema-tolerant for nested dashboard summaries; if backend field names evolve, fallback labels may show `UNKNOWN` rather than crashing.
- Some production sources may still return `MISSING`, `PARTIAL`, or empty arrays until runtime data exists; the UI represents that honestly.

## Phase Status

GREEN.

## Can Continue To Stage 11, Money Visibility Pages?

YES.
