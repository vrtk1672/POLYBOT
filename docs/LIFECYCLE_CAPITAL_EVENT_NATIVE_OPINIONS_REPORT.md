# POLYBOT Phase 9B - Lifecycle / Capital Event-Native Opinions Report

## Purpose

Phase 9B makes Capital and Lifecycle participate inside the same event-driven Mesh session as Liquidity, Risk, Exit, and Coordinator for `orderbook.snapshot.created`.

The phase keeps execution disabled. It records event-native opinions and coordinator trace only.

## Current Reality Found

Before implementation, latest active bundles were source-backed but partial:

- Liquidity, Risk, and Exit were event-native brain outputs.
- Coordinator trace existed.
- Capital and Lifecycle were joined from historical/source-backed tables where available.
- Lifecycle could be stale/conflicting relative to the fresh orderbook event.
- Event proof counted zero event-native capital/lifecycle reactions.

## Existing Sources Reused

- `event_log`
- `event_consumers`
- `event_delivery_attempts`
- `brain_outputs`
- `coordinator_decisions`
- `coordinator_decision_inputs`
- `orderbook_snapshots`
- `paper_accounts`
- `paper_positions`
- `lifecycle_governance_decisions`
- `paper_eligibility_candidates`

No migration was required.

## Capital Event-Native Implementation

The orderbook mesh consumer now writes a Capital brain output for the same event/correlation as the orderbook snapshot event.

Capital opinion metadata includes:

- `event_native_state=EVENT_NATIVE`
- `capital_opinion_state`
- `available_capital`
- `locked_capital`
- `open_exposure`
- blockers/warnings

The implementation only reads capital state. It does not allocate, reserve, or mutate balances.

## Lifecycle Event-Native Implementation

The orderbook mesh consumer now writes a Lifecycle brain output for the same event/correlation.

Lifecycle opinion metadata includes:

- `event_native_state=EVENT_NATIVE`
- `lifecycle_opinion_state`
- `decision_source`
- `source_created_at`
- blockers/warnings

Lifecycle lookup now prefers:

1. candidate-specific lifecycle decision
2. market plus side/token constrained lifecycle decision

It does not create approvals or bypass governance.

## Coordinator Five-Opinion Behavior

Coordinator now consumes:

- liquidity
- risk
- exit
- capital
- lifecycle

Phase-level decisions are stored in coordinator metadata:

- `PRICE_READY`
- `PRICE_BLOCKED`
- `WAITING_FOR_CAPITAL`
- `WAITING_FOR_LIFECYCLE`
- `CAPITAL_BLOCKED`
- `LIFECYCLE_BLOCKED`
- `WAITING_FOR_EVIDENCE`

The DB `final_state` remains mapped to the existing safe vocabulary. `execution_allowed` remains false.

## Files Inspected

- `AGENTS.md`
- `docs/POLYBOT_AGENT_DISPATCH_PROTOCOL.md`
- `docs/MINIMAL_EVENT_DRIVEN_MESH_PROOF_REPORT.md`
- `docs/MESH_SESSION_EVIDENCE_BUNDLE_REPORT.md`
- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/mesh_evidence_bundle.py`
- `app/services/paper_capital.py`
- `app/services/paper_dashboard_truth.py`
- `app/control_center/paper_readiness.py`
- `tests/test_event_mesh_proof.py`
- `tests/test_mesh_evidence_bundle.py`

## Files Changed

- `app/events/consumers/orderbook_mesh_consumer.py`
- `app/control_center/event_mesh_proof.py`
- `app/control_center/mesh_evidence_bundle.py`
- `frontend/control-center/src/pages/CommandCenterHome.tsx`
- `tests/test_lifecycle_capital_event_native_opinions.py`
- `tests/test_event_mesh_proof.py`
- `tests/test_mesh_evidence_bundle.py`
- `docs/LIFECYCLE_CAPITAL_EVENT_NATIVE_OPINIONS_REPORT.md`

## APIs Changed

No new route was added.

Extended response fields:

- `/dashboard/api/v2/control/event-mesh-proof`
  - `events_with_capital_reaction`
  - `events_with_lifecycle_reaction`
  - `events_with_all_five_reactions`
  - `events_with_event_native_capital`
  - `events_with_event_native_lifecycle`

- `/dashboard/api/v2/control/mesh-evidence-bundles`
  - `with_event_native_capital`
  - `with_event_native_lifecycle`
  - `with_all_five_opinions`
  - `mesh_consensus_state`
  - capital/lifecycle `event_native_state`

## Frontend Changes

Control Center now displays:

- Capital Brain reaction count
- Lifecycle Brain reaction count
- all-five reaction count
- Capital event-native state
- Lifecycle event-native state
- Mesh consensus state

No mock data was introduced.

## Tests Added

`tests/test_lifecycle_capital_event_native_opinions.py`

Coverage:

- Capital opinion is created for an orderbook event.
- Lifecycle opinion is created for an orderbook event.
- Both share event/correlation.
- Both are marked `EVENT_NATIVE`.
- Coordinator consumes all five opinions.
- Lifecycle denial produces `LIFECYCLE_BLOCKED`.
- No paper artifacts are created.

Existing tests updated:

- `tests/test_event_mesh_proof.py`
- `tests/test_mesh_evidence_bundle.py`

## Tests Run

Local unit environment:

- `.venv\Scripts\python.exe -m pytest tests/test_lifecycle_capital_event_native_opinions.py -q -rs`
  - Result: `3 skipped`
  - Reason: `POLYBOT_DATABASE_URL is not configured`

- `.venv\Scripts\python.exe -m pytest tests/test_lifecycle_capital_event_native_opinions.py tests/test_event_mesh_proof.py tests/test_mesh_evidence_bundle.py -q -rs`
  - Result: `11 skipped`
  - Reason: DB-backed tests skipped because `POLYBOT_DATABASE_URL` is not configured

- `.venv\Scripts\python.exe -m pytest tests/test_event_mesh_proof.py tests/test_mesh_evidence_bundle.py tests/test_candidate_price_path.py tests/test_paper_readiness.py tests/test_control_center_read_only_apis.py -q -rs`
  - Result: `6 passed, 28 skipped`

- `.venv\Scripts\python.exe -m pytest tests -q -k "mesh or event or coordinator or brain or capital or lifecycle"`
  - Result: `127 passed, 362 skipped, 1448 deselected`

- `.venv\Scripts\python.exe -m compileall app tests`
  - Result: passed

- `npm run typecheck`
  - Result: passed

- `npm run test -- src/lib/truth-contract.test.ts src/components/truth/truth-components.test.tsx src/api/controlCenterClient.test.ts`
  - Result: `3 passed`, `18 tests passed`

- `npm run build`
  - Result: passed
  - Note: Vite chunk-size warning only.

## Deployment / Restart Results

Port 8000 owner:

- Docker container `polybot_api`

Deployment action:

- `docker compose build api`
- `docker compose up -d --no-deps api`

Only the API container was recreated. DB volumes were not reset or deleted.

## Controlled SYSTEM ON Smoke Procedure

Baseline:

- Paper Simulation OFF
- Runtime STOPPED
- Paper readiness BLOCKED
- Full Monitor Run not started

Action:

- POST SYSTEM ON through official Control Center action endpoint
- Waited 150 seconds while polling GET-only truth endpoints
- POST SYSTEM OFF through official Control Center action endpoint

Forbidden actions were not called.

## Before / After Opinion and Coordinator Counts

Before:

- `brain_outputs`: 20862
- `coordinator_decisions`: 20634
- `coordinator_decision_inputs`: 20862
- `event_delivery_attempts`: 384
- `orderbook_snapshots`: 51008

After:

- `brain_outputs`: 21112
- `coordinator_decisions`: 20692
- `coordinator_decision_inputs`: 21112
- `event_delivery_attempts`: 672
- `orderbook_snapshots`: 51056

These increases are expected Mesh proof artifacts from DATA_ONLY orderbook events and brain/coordinator trace writes.

`capital_brain_evaluations` stayed 192.

`lifecycle_governance_decisions` increased from 10751 to 10752 due the existing DATA_ONLY candidate/lifecycle path creating a new HARD_BLOCK decision:

- `allow_paper_intent=false`
- `allow_paper_execution=false`
- blockers: `STALE_CAPITAL_EVALUATION`, `STALE_ORDERBOOK`

This did not loosen lifecycle approval.

## Sample All-Five Bundle

Latest active sample:

- correlation: `live_orderbook_watcher_1d21a94315e440349bb2c9f9a4e93748:ob_402a780c44004c48b7a2462ad782a6fd`
- market: `691547`
- side: `NO`
- event proof: `PROVEN`
- bundle state: `COMPLETE`
- opinion states:
  - liquidity: `PRESENT`
  - risk: `PRESENT`
  - exit: `PRESENT`
  - capital: `PRESENT`
  - lifecycle: `PRESENT`
- capital opinion state: `CAPITAL_OK`
- lifecycle opinion state: `LIFECYCLE_DENIED`
- coordinator decision: `LIFECYCLE_BLOCKED`
- consensus: `CONSENSUS_BLOCKED`
- execution allowed: `false`

## Conflict Results

The prior false conflict pattern, `LIFECYCLE_DENIED_COORDINATOR_PRICE_READY`, is resolved for new event-native bundles.

Current sample has no conflict because coordinator correctly blocks on lifecycle:

- `LIFECYCLE_DENIED`
- `LIFECYCLE_BLOCKED`
- `CONSENSUS_BLOCKED`

## Candidate / Bridge Integration

`MeshEvidenceBundleService.latest_bundle_link()` now returns:

- `mesh_capital_opinion_state`
- `mesh_lifecycle_opinion_state`
- `mesh_capital_event_native_state`
- `mesh_lifecycle_event_native_state`
- `mesh_consensus_state`
- `mesh_coordinator_decision`
- `mesh_conflicts`

Candidate explanation and eligible-to-intent bridge surfaces that already consume the latest bundle link can now display the capital/lifecycle event-native truth when a candidate-linked bundle exists.

Current active candidate samples still often lack direct event correlation because candidate linkage from orderbook events remains partial for historical/default rows.

## Paper Readiness Before / During / After

Before:

- `paper_readiness_state=BLOCKED`
- `runtime_life_state=STOPPED`
- `paper_simulation_state=OFF`

During SYSTEM ON:

- event mesh proof became `PROVEN`
- mesh evidence bundle became `COMPLETE`
- paper readiness stayed `BLOCKED`
- paper simulation stayed `OFF`

After SYSTEM OFF:

- runtime returned `STOPPED`
- paper readiness `BLOCKED`
- paper simulation `OFF`

## Artifact Safety Counts

Forbidden artifacts before / after:

- `paper_intents`: 20 -> 20
- `paper_orders`: 12 -> 12
- `paper_fills`: 9 -> 9
- `paper_positions`: 12 -> 12
- `live_orders`: 0 -> 0
- `positions`: 0 -> 0

No paper/live/shadow artifacts were created.

## Remaining Risks

- Candidate linkage remains partial when orderbook events do not carry `candidate_id`.
- New bundles can be complete and blocked by lifecycle, which is correct but means not all complete bundles are ready.
- Local DB-backed tests skipped without `POLYBOT_DATABASE_URL`; active container smoke exercised the real DB path.

## Next Recommended Phase

Candidate/event correlation hardening: ensure candidate-targeted orderbook events consistently include `candidate_id` so candidate explanations and eligible bridge can always link to the exact Mesh evidence room.
