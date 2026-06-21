# Full Mesh Deep Inquiry for Proactive Seeds - Stage 5 Report

## Purpose

Stage 5 adds the safe persisted DATA_ONLY contract between proactive research-only candidate seeds and future Full Mesh deep inquiry. It converts seed handoff from an implicit skipped state into auditable request/result truth without creating execution candidates, paper artifacts, orders, capital allocation, or fake Mesh approvals.

## Money Machine Fit

The Money Machine path now has a persisted bridge:

source event -> event-to-market recall -> targeted revalidation -> proactive candidate seed -> research priority watchlist -> seed Mesh inquiry request/result.

Stage 5 deliberately stops before actual Full Mesh invocation because no reviewed proactive-seed DATA_ONLY Mesh input adapter exists yet.

## Existing Contract Audit

The existing Full Mesh inquiry service is DATA_ONLY, but it is built around existing Mesh evidence bundle inputs. Stage 4 correctly skipped Mesh handoff because proactive candidate seeds did not have a persisted, reviewed Mesh input contract. No safe execution-adjacent shortcut was used.

## Architecture

Added `ProactiveSeedMeshInquiryService` with:

- strict seed selection policy
- persisted inquiry request rows
- persisted result rows
- run audit rows with safety counts
- endpoint/control wrappers
- source-refresh orchestrator registration
- read-only integration helpers for downstream surfaces

Clean seeds are persisted as `SKIPPED` with `SAFE_MESH_CONTRACT_MISSING`, preserving lineage and proving they are eligible for a future DATA_ONLY adapter review. Unsafe seeds are persisted as `BLOCKED` with exact blockers.

## Data Model

Migration `0138_proactive_seed_mesh_inquiry.sql` creates:

- `proactive_seed_mesh_inquiries`
- `proactive_seed_mesh_results`
- `proactive_seed_mesh_inquiry_runs`

Every inquiry stores seed/source/revalidation/watchlist lineage, market identity, side/token, priority, DATA_ONLY handoff mode, all execution flags false, blockers, warnings, and required-to-pass details.

Every result stores result state, Edge/Thesis/Score/Risk/Capital/Exit/Lifecycle visibility fields, Paper Observation/Full Paper flags, blockers, and a mesh summary.

## Selection Policy

Selected only:

- `seed_state = GENERATED`
- `research_only = true`
- `execution_allowed = false`
- `paper_allowed = false`
- `shadow_allowed = false`
- `live_allowed = false`
- side is `YES` or `NO`
- token and market identity present
- orderbook is `FRESH`
- token-side state is direct/directional
- priority is `HIGH` or `MEDIUM`
- not recently processed

Skipped or blocked:

- `SIDE_UNKNOWN`
- `WATCH_ONLY`
- `BLOCKED`
- stale orderbook
- token-side unknown/conflict
- LOW/DORMANT/ARCHIVED priority by default
- any seed with execution/paper/shadow/live flag true

## Mesh Handoff Contract

Actual Full Mesh invocation remains blocked by design:

`SAFE_MESH_CONTRACT_MISSING`

This avoids fake Edge, fake thesis, fake score, fake Mesh approval, and any accidental execution-adjacent write.

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry`
- `POST /dashboard/api/v2/control/proactive-seed-mesh-inquiry/refresh`
- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-seed`
- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-market`
- `GET /dashboard/api/v2/control/proactive-seed-mesh-inquiry/by-event`

Updated integration visibility in proactive candidate generation, research priority watchlist, targeted revalidation, source event memory, market memory via existing helpers, trade opportunity score, paper actionability, and decision propagation trace.

## Verification Counts

Final Stage 5 persisted rows:

- proactive seeds: 387
- seed Mesh inquiries: 260
- seed Mesh results: 260
- skipped clean DATA_ONLY requests: 165
- blocked requests: 95
- completed/sent requests: 0
- latest run: 20 seeds available, 20 selected, 20 requests created, 20 skipped, 0 blocked, 20 results created

Result state counts:

- `SKIPPED / UNKNOWN Edge / UNKNOWN Thesis / UNKNOWN band`: 165
- `BLOCKED / UNKNOWN Edge / UNKNOWN Thesis / UNKNOWN band`: 95

Paper Observation eligible from Mesh-reviewed seeds: 0
Full Paper ready from Mesh-reviewed seeds: 0

## Examples

Clean skipped DATA_ONLY seed:

- seed: `proactive_seed_a709596694ac5594ba2acfb12daeb7e5`
- market: `691547`
- side: `YES`
- priority: `HIGH`, score `82`
- request state: `SKIPPED`
- blocker: `SAFE_MESH_CONTRACT_MISSING`
- reason: create/review proactive-seed DATA_ONLY Mesh adapter before invoking Full Mesh

Blocked seed:

- seed: `proactive_seed_69c170e3eb5f2c888d3412593e8d231a`
- market: `691547`
- side: `SIDE_UNKNOWN`
- request state: `BLOCKED`
- blockers: `SEED_STATE_NOT_GENERATED_BLOCKED`, `SIDE_NOT_MESH_ELIGIBLE`, `TOKEN_ID_MISSING`, `ORDERBOOK_NOT_FRESH`, `REVALIDATION_NOT_CLEAN_PARTIAL`, `REVALIDATION_NOT_CANDIDATE_GENERATION_ELIGIBLE`

## DATA_ONLY Verification

Actions performed:

- deployed API and migration image
- migration runner reported no pending migrations after initial apply
- verified `/healthz`
- triggered Stage 5 refresh
- POSTed SYSTEM ON for DATA_ONLY verification
- waited through supervisor/source cycles
- verified `/runtime/health`
- verified Stage 5 endpoint, by-seed, by-market, and decision propagation trace
- POSTed SYSTEM OFF cleanup

Runtime after cleanup:

- system power: OFF
- current mode: DATA_ONLY
- runtime state: STOPPED / SAFE_STOPPED
- Paper Simulation: OFF
- Shadow: disabled
- Live: disabled

## Safety Counts

Before Stage 5 final verification:

- paper_intents: 21
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- live_orders: 0
- positions: 0
- shadow_orders: 0

After Stage 5 final verification:

- paper_intents: 21
- paper_orders: 12
- paper_fills: 9
- paper_positions: 12
- live_orders: 0
- positions: 0
- shadow_orders: 0

No execution candidate table rows were created by Stage 5; `fresh_candidate_seeds` remained 22 and `market_link_candidates` remained 0.

## Tests

Focused:

`19 passed in 0.83s`

Related:

`16 passed, 7 skipped in 2.93s`

Broad:

`72 passed, 15 skipped, 2146 deselected in 6.15s`

Compile:

`compileall app tests` completed successfully.

## Limitations

Actual Full Mesh invocation is intentionally not implemented. Stage 5 creates the safe persisted DATA_ONLY request/result contract and exposes exact readiness. The next stage should implement and review a proactive-seed DATA_ONLY Mesh input adapter before any seed is sent into Full Mesh computation.

## Safety Result

GREEN for Stage 5 DATA_ONLY persisted contract.

Safe for next DATA_ONLY stage: YES.
Safe for Paper Observation execution: NO.
Safe for Shadow: NO.
Safe for Live: NO.

## Recommended Next Step

Implement the reviewed proactive-seed DATA_ONLY Mesh adapter that consumes `proactive_seed_mesh_inquiries` with `SAFE_MESH_CONTRACT_MISSING`, invokes Full Mesh without execution permissions, and writes real Edge/Thesis/Score lineage only when supported by existing Mesh contracts.
