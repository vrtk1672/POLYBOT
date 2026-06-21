# POLYBOT Control Center V1.5 - Stage 12 React Flow Decision Graph Report

Date: 2026-06-08
Executor: Codex
Task mode: CONTROLLED_FEATURE
Risk: MEDIUM
ChatGPT review: REQUIRED by prompt
Codex review: Not required; no backend/API/runtime/trading changes were made.

## Purpose

Stage 12 adds an advanced read-only decision visualization layer for the Decision Intelligence area using the free/open-source React Flow package `@xyflow/react`.

The graph layer visualizes existing Stage 5 read-only Truth Contract data through the Stage 8 query layer. It does not replace the Stage 10 table/list views.

## Current Reality Found

- `frontend/control-center` already had a Vite/React/TanStack Query frontend with Stage 9 core pages, Stage 10 Decision Intelligence pages, and Stage 11 money pages.
- `@xyflow/react` was not installed before Stage 12:
  - `npm ls @xyflow/react` returned `(empty)` before install.
- Existing Decision Intelligence pages lived in `frontend/control-center/src/pages/decisionIntelligence.tsx`.
- Existing hooks already existed:
  - `useDecisionXrayQuery`
  - `useRiskEvidenceQuery`
  - `useLifecycleGovernanceQuery`
  - `useMeshDialoguesQuery`
  - `useBlockersQuery`
  - `useClosestActionableQuery`
- Existing endpoints already existed:
  - `/dashboard/api/v2/control/decision-xray`
  - `/dashboard/api/v2/control/blockers`
  - `/dashboard/api/v2/control/closest-actionable`
  - `/dashboard/api/v2/control/truth-state`
  - `/dashboard/api/v2/control/risk-evidence`
  - `/dashboard/api/v2/control/lifecycle-governance`
  - `/dashboard/api/v2/control/mesh-dialogues`
- No backend graph-specific endpoint existed, and none was needed.
- The graph adapter uses existing nested summaries and row arrays. When source rows are missing, it returns empty graph state with explicit missing/partial messages.

## Files Created

- `frontend/control-center/src/pages/DecisionGraph.tsx`
- `frontend/control-center/src/pages/decisionGraphAdapter.ts`
- `frontend/control-center/src/pages/decisionGraph.test.tsx`
- `docs/CONTROL_CENTER_STAGE_12_REACT_FLOW_DECISION_GRAPH_REPORT.md`

## Files Changed

- `frontend/control-center/package.json`
- `frontend/control-center/package-lock.json`
- `frontend/control-center/src/pages/decisionIntelligence.tsx`
- `frontend/control-center/src/pages/decisionIntelligence.test.tsx`
- `frontend/control-center/src/test/setup.ts`

## Files Deleted

None.

## Dependency Added

| Dependency | Purpose | Free/Open-source? | Notes |
| ---------- | ------- | ----------------- | ----- |
| `@xyflow/react@12.11.0` | Read-only React Flow graph rendering for Decision Intelligence panels | YES | No React Flow Pro, paid layout, paid node pack, cloud, or license-key package was added. |

## Graph Types Created

| Graph | Source hooks/data | What it shows | Truth behavior |
| ----- | ----------------- | ------------- | -------------- |
| Decision X-Ray graph | `decision-xray` envelope / `risk_evidence.latest_evaluations`, blocker maps, critical missing maps | Candidate/evidence/blocker chain from backend risk evidence rows | Empty/missing state if source or rows are absent; no approval inferred. |
| Conflict Map graph | `risk-evidence` envelope / blocker subtype, critical missing, optional missing, risk-source selection summaries | Risk blockers, non-risk missing evidence, optional gaps, selected risk source | Shows only supplied maps/rows; no missing blocker invented. |
| Candidate Lifecycle graph | `lifecycle-governance` envelope / latest decisions, risk review traces, critical blocker summaries, risk source selection | Candidate-to-lifecycle-gate relationships and still-blocking non-risk gates | Preserves actionability labels as backend facts only; does not infer actionability. |
| Brain Flow graph | `mesh-dialogues` envelope / `mesh_dialogues.events` | Brain/source dialogue events and emitted event types | Empty graph when no dialogue events exist; no dialogue invented. |

## Adapter Logic

- `decisionGraphAdapter.ts` converts one already-fetched Truth Contract envelope into graph model data.
- It creates nodes only from:
  - envelope source
  - backend row identifiers such as `subject_id`, `candidate_id`, `market_id`, `evaluation_id`, `decision_id`
  - backend map keys such as blocker subtype names and critical missing evidence names
  - backend dialogue event fields
- It creates no nodes when:
  - source is missing
  - status is `ERROR`
  - no backend rows/maps exist for the selected graph type
- It preserves envelope `status`, `truth_state`, and `source`.
- It never upgrades `PARTIAL`, `MISSING`, `STALE`, `ERROR`, or `NOT_IMPLEMENTED`.
- It does not infer approval, actionability, blockers, or dialogue.

## Component Behavior

- `DecisionGraph.tsx` renders React Flow in read-only mode.
- Disabled:
  - node dragging
  - node connecting
  - node selection
  - edge focus
  - node focus
- No graph controls that trigger backend calls or persist layout are exposed.
- The component accepts already-fetched truth envelopes as props.
- It makes no direct API calls.
- It displays source, status, truth_state, node count, edge count, and missing-state messages.

## Tests Added

- `frontend/control-center/src/pages/decisionGraph.test.tsx`

The tests prove:

- adapter creates nodes from provided backend-like evidence data
- adapter does not invent missing blockers
- adapter returns missing/empty graph when source is missing
- stale legacy/risk source and non-risk blocker nodes appear only when supplied
- `DecisionGraph` renders missing state honestly
- `DecisionGraph` renders evidence/blocker nodes from provided data
- graph panel appears in Decision X-Ray page
- Brain Flow graph uses real dialogue events only
- no fake approval, fake green, fake PnL, fake runtime status, or dangerous controls appear

Updated:

- `frontend/control-center/src/pages/decisionIntelligence.test.tsx`
  - Adjusted assertions where graph panels now display duplicate source-backed facts already shown in list/table views.

- `frontend/control-center/src/test/setup.ts`
  - Added a jsdom `ResizeObserver` stub required by React Flow tests.

## Tests Run And Exact Results

From `frontend/control-center`:

- `npm test -- --run src/pages/decisionGraph.test.tsx`
  - Result: PASS
  - Test files: 1 passed
  - Tests: 8 passed
- `npm test -- --run src/pages/decisionIntelligence.test.tsx`
  - Result: PASS
  - Test files: 1 passed
  - Tests: 8 passed
- `npm test -- --run src/pages/moneyVisibility.test.tsx`
  - Result: PASS
  - Test files: 1 passed
  - Tests: 9 passed
- `npm test`
  - Result: PASS
  - Test files: 9 passed
  - Tests: 59 passed
- `npm run typecheck`
  - Result: PASS
  - `tsc --noEmit`
- `npm run build`
  - Result: PASS
  - Vite built successfully.
  - Note: Vite emitted a chunk-size warning after React Flow increased the JS bundle to `524.40 kB` minified.
- `npm audit --audit-level=high`
  - Result: PASS
  - `found 0 vulnerabilities`
- `npm ls @xyflow/react`
  - Result: PASS
  - Installed: `@xyflow/react@12.11.0`
- `npm ls --depth=0`
  - Result: PASS
  - Dependency tree listed successfully.

Repo-level:

- React Flow Pro / license-key scan:
  - Result: PASS, no matches.
- Non-test mutating helper / dangerous-control scan:
  - Result: PASS, no matches.
- Invented-claim scan:
  - Result: PASS for safety; matches were only existing copy stating no invented blockers/dialogue.
- `git status --short`
  - Result: NOT AVAILABLE
  - Reason: `fatal: not a git repository (or any of the parent directories): .git`

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
| only GET read-only data visualized | YES |
| no POST/PUT/PATCH/DELETE helper added | YES |
| no dangerous controls exposed | YES |
| no fake green introduced | YES |
| no fake approval introduced | YES |
| no fake PnL introduced | YES |
| no fake runtime status introduced | YES |
| no invented blockers | YES |
| no invented dialogue | YES |
| no invented actionability | YES |
| MISSING/PARTIAL/STALE preserved honestly | YES |
| React Flow free package only | YES |
| no paid/pro/cloud-only/license-key package added | YES |
| frontend tests passed | YES |
| frontend build passed | YES |
| frontend typecheck passed | YES |
| npm audit passed | YES |

## Remaining Risks

- Graph richness is limited by existing Stage 5 envelopes. The UI shows empty/missing graph state when backend rows/maps are absent.
- The adapter is intentionally schema-tolerant because existing dashboard payloads are generic Truth Contract data. If backend graph contracts become explicit later, the adapter should become stricter.
- React Flow increased the production JS bundle and Vite emitted a chunk-size warning. This is not a build failure, but future frontend performance work may split the graph code.
- Browser visual QA was not run because the allowed command list did not include starting a dev server.
- Git metadata is unavailable in this workspace folder, so changed-file state cannot be verified with `git status`.

## Next Recommended Phase

Continue with the next planned frontend visibility/control-center phase after ChatGPT review. A useful next step would be explicit UI visual QA or code-splitting for graph-heavy panels, still without adding backend mutations or controls.

## Phase Status

GREEN.

Stage 12 React Flow Decision Graph is implemented with the free React Flow package, existing read-only hooks/endpoints, no backend changes, no dangerous controls, no invented evidence, and passing tests/build/typecheck/audit.

## Can Continue To Next Stage

YES.
