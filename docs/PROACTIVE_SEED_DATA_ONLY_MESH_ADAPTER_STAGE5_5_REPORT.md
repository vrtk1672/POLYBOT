# Proactive Seed DATA_ONLY Mesh Adapter Stage 5.5 Report

## 1. Purpose

Stage 5.5 implements the missing DATA_ONLY adapter between persisted proactive seed Mesh inquiry requests and the existing read-only Full Mesh inquiry path.

The goal was to move clean requests beyond `SAFE_MESH_CONTRACT_MISSING` without creating execution candidates, paper artifacts, orders, capital allocation, Shadow, or Live behavior.

## 2. Money Machine Fit

The Stage 5.5 adapter completes the safe research bridge:

source event -> recall link -> targeted revalidation -> proactive research seed -> seed Mesh inquiry -> DATA_ONLY Mesh review -> Edge/Thesis/Score/Risk/Capital/Exit/Lifecycle visibility.

It still does not trade. Paper Observation remains classification only.

## 3. Existing Mesh Contract Audit

Findings:

- `FullMeshInquiryOrchestrator.build_session(...)` is the existing read-only Mesh inquiry path.
- `build_edge_thesis_from_mesh_responses(...)` provides deterministic source-backed edge truth from Mesh organ responses.
- `build_trade_thesis(...)` can evaluate a research seed payload without execution.
- `score_actionability_item(...)` can produce deterministic opportunity score and decision band without writing paper artifacts.
- No safe persisted proactive-seed input payload existed before this stage; Stage 5 therefore skipped requests with `SAFE_MESH_CONTRACT_MISSING`.
- No existing pure research candidate table was required for Stage 5.5; synthetic candidate ids use the `research_seed_candidate_...` namespace and are stored only in adapter payload/result metadata.

## 4. Architecture

Added `ProactiveSeedDataOnlyMeshAdapter`.

The adapter:

- selects only clean Stage 5 inquiry requests with `SAFE_MESH_CONTRACT_MISSING`;
- revalidates seed safety flags and evidence;
- writes a DATA_ONLY adapter payload row;
- invokes `FullMeshInquiryOrchestrator` with a research-only candidate-like bundle;
- builds deterministic thesis and opportunity score from the Mesh result;
- persists result state back to `proactive_seed_mesh_results`;
- updates the inquiry request state to `MESH_DATA_ONLY_COMPLETED`, `PARTIAL`, `BLOCKED`, or `FAILED`.

## 5. Adapter Input Policy

Accepted only when:

- request is `SKIPPED` or `PENDING`;
- request blocker is `SAFE_MESH_CONTRACT_MISSING` or `ADAPTER_PENDING`;
- seed state is `GENERATED`;
- `research_only=true`;
- all execution/paper/shadow/live flags are false;
- side is `YES` or `NO`;
- token id and market id exist;
- orderbook refresh state is `FRESH`;
- token-side resolution is direct/directional;
- candidate event scope is `CANDIDATE_SCOPED`;
- priority is `HIGH` or `MEDIUM`.

Rejected/skipped:

- `SIDE_UNKNOWN`, `WATCH_ONLY`, `BLOCKED`, stale orderbook, token-side unknown/conflict, missing token, unsafe flags, low priority, or uncertain safety.

## 6. Adapter Payload Model

Added `proactive_seed_mesh_adapter_payloads` with:

- `adapter_payload_id`
- `seed_mesh_inquiry_id`
- `proactive_candidate_seed_id`
- `synthetic_candidate_id`
- lineage ids
- market/condition/side/token ids
- orderbook snapshot id
- link and direction confidence
- all safety flags
- serialized payload, lineage, and safety JSON.

All payloads are:

- `research_only=true`
- `execution_allowed=false`
- `paper_allowed=false`
- `shadow_allowed=false`
- `live_allowed=false`

## 7. Mesh / Edge / Thesis / Score Integration

The adapter uses the existing read-only Mesh orchestrator and deterministic builders.

Persisted outputs include:

- Mesh session id where created
- Edge state
- Trade Thesis state
- Opportunity score
- Opportunity decision band
- Risk state
- Capital state
- Exit state
- Lifecycle state
- Paper Observation eligible classification
- Full Paper ready classification
- hard blockers
- soft blockers
- required_to_improve

No result grants execution authority.

## 8. Safety Isolation

The adapter records safety counts before and after each run for:

- paper intents
- paper orders
- paper fills
- paper positions
- live orders
- positions
- shadow orders
- execution candidate tables used in this repo

The latest run recorded `trading_mutation=false`.

## 9. Result States

- `MESH_DATA_ONLY_COMPLETED`: Full DATA_ONLY review completed without Mesh organ error.
- `PARTIAL`: review produced useful truth, but at least one read-only Mesh organ errored or a component could not complete safely.
- `BLOCKED`: seed/request failed adapter input policy.
- `FAILED`: adapter could not safely invoke or persist result.

During verification, 27 initially completed rows were corrected to `PARTIAL` because the Mesh session state was `ERROR` even though Edge/Thesis/Score were produced. This is a DATA_ONLY truth correction, not an execution mutation.

## 10. Deduplication And Rate Limiting

The adapter deduplicates by:

- `seed_mesh_inquiry_id`
- adapter payload id derived from inquiry id
- existing completed/recent payload rows unless forced

Default limits:

- manual endpoint default: 25
- source-refresh hook: 10 per cycle
- HIGH/MEDIUM priority only

## 11. API Changes

Added:

- `POST /dashboard/api/v2/control/proactive-seed-mesh-inquiry/run-adapter`
- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry/adapter-diagnostics`

Updated:

- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry`
- seed/market summary metadata
- opportunity score output fields:
  - `seed_mesh_adapter_payload_id`
  - `seed_mesh_adapter_result_state`

## 12. Integration Surfaces

Integrated into:

- proactive seed Mesh inquiry summary
- proactive candidate generation through existing seed Mesh fields
- research priority watchlist through existing seed Mesh result fields
- opportunity score metadata
- paper actionability visibility through score/actionability surfaces
- source-refresh orchestrator as a conservative DATA_ONLY hook

## 13. Tests Run

Focused:

- `tests/test_proactive_seed_mesh_adapter.py`
- `tests/test_seed_mesh_adapter_safety.py`
- `tests/test_seed_mesh_adapter_results.py`
- `tests/test_seed_mesh_adapter_integration_surfaces.py`

Result: `19 passed`.

Related:

- Stage 5 inquiry tests
- opportunity scoring
- paper actionability strict qualification

Result: `32 passed`.

Broad filtered:

- `seed_mesh_adapter or proactive_seed_mesh or seed_mesh or opportunity_score or paper_actionability or decision_trace or source_backed_edge or trade_thesis`

Result: `90 passed, 2 skipped, 2160 deselected`.

Final targeted sanity after diagnostics correction:

- `27 passed`.

Compile:

- `.venv\Scripts\python.exe -m compileall app tests`

Result: passed.

## 14. DATA_ONLY Verification

Deployment:

- `docker compose build api`
- `docker compose build migrate`
- `docker compose run --rm migrate`
- `docker compose up -d --no-deps api`

Migration applied:

- `0139_proactive_seed_data_only_mesh_adapter.sql`

Controlled verification:

1. Triggered Market Universe Memory refresh.
2. Triggered Source Event Memory refresh.
3. Triggered Targeted Market Revalidation refresh.
4. Triggered Proactive Candidate Generation refresh.
5. Triggered Research Priority Watchlist refresh.
6. Triggered Proactive Seed Mesh Inquiry refresh.
7. Triggered adapter run.
8. Posted SYSTEM ON.
9. Waited 4 DATA_ONLY supervisor cycles.
10. Posted SYSTEM OFF.

Final runtime state:

- `SAFE_STOPPED`
- `DATA_ONLY`
- system power `OFF`
- supervisor `REGISTERED_NOT_RUNNING`

## 15. Adapter Processed Counts

Final adapter diagnostics:

- adapter payloads: 65
- adapter processed: 65
- `MESH_DATA_ONLY_COMPLETED`: 38
- `PARTIAL`: 27
- failed: 0
- blocked by adapter: 0
- skipped by adapter: 0

## 16. Mesh / Edge / Thesis / Score Counts

Final seed Mesh results:

- `EDGE_SUPPORTED`: 65
- `THESIS_SUPPORTED`: 17
- `THESIS_WATCH`: 48
- `PAPER_OBSERVATION`: 17
- `HARD_BLOCKED`: 48
- Full Paper ready: 0

Remaining Stage 5 skipped requests:

- `SAFE_MESH_CONTRACT_MISSING`: 200

This increased during SYSTEM ON because the DATA_ONLY source-refresh chain created additional Stage 5 requests while the adapter also processed 65.

## 17. Example Result

Example completed DATA_ONLY adapter result:

- seed: `proactive_seed_91ffbc6b82d81cc51a6058af4ded34f3`
- market: `691547`
- side: `YES`
- request: `seed_mesh_inquiry_29dfd85397c1ff7952fee79a1e7b`
- adapter payload: `seed_mesh_adapter_payload_de11e8a4a8e1b78f1ced57d12059`
- result state after stricter correction: `PARTIAL`
- Edge: `EDGE_SUPPORTED`
- Thesis: `THESIS_SUPPORTED`
- Score: `61.99`
- Band: `PAPER_OBSERVATION`
- Paper Observation eligible: true, classification only
- Full Paper ready: false
- Remaining blockers: `capital_watch_not_full_paper_ready`, `reward_evidence_weak_or_missing`

## 18. Safety Result

Before / after artifact counts:

- paper_intents: 21 -> 21
- paper_orders: 12 -> 12
- paper_fills: 9 -> 9
- paper_positions: 12 -> 12
- live_orders: 0 -> 0
- positions: 0 -> 0
- shadow_orders: 0 -> 0
- fresh_candidate_seeds: 22 -> 22
- market_link_candidates: 0 -> 0

No paper/live/shadow/execution artifacts were created.

## 19. Limitations

- Some Mesh reviews are `PARTIAL` because at least one read-only organ can error while other evidence paths still produce Edge/Thesis/Score.
- Remaining `SAFE_MESH_CONTRACT_MISSING` requests are normal backlog created by ongoing DATA_ONLY seed generation.
- Full Paper readiness remains zero because capital and reward evidence are still not strict Full Paper quality.
- Paper Observation execution is still not implemented and remains not allowed.

## 20. Recommended Next Stage

Recommended next step:

Paper Observation Policy Review only after operator acceptance that Stage 5.5 Mesh-reviewed seed results are sufficient. Otherwise, improve the Mesh adapter and source organs to reduce `PARTIAL` outcomes and expand universe coverage.
