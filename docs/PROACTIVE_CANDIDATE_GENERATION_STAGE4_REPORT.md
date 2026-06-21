# Proactive Candidate Generation Stage 4 Report

## Purpose

Stage 4 adds DATA_ONLY proactive candidate seed generation from clean targeted market revalidation truth.

It turns:

source event -> market recall -> targeted revalidation -> research-only candidate seed

into a queryable Control Center surface without creating execution candidates, paper artifacts, live artifacts, or Mesh approvals.

## Money Machine Fit

POLYBOT is moving from passive candidate analysis toward proactive opportunity hunting. Stage 4 is the first candidate-hypothesis layer after Market Universe Memory, Source Event Memory, Smart Recall, and Targeted Market Revalidation.

This stage does not trade. It creates research-only seeds that later stages can send through a safe Full Mesh deep inquiry path.

## Existing Candidate-Generation Audit

- Existing `paper_eligibility_candidates` is paper/execution-facing and is not safe for Stage 4 seed writes.
- Existing `fresh_candidate_seeds` participates in older candidate conversion paths and is not safe for this research-only layer.
- Existing `market_link_candidates` is an older phase candidate table and is not the canonical Stage 4 surface.
- Existing `FullMeshInquiryOrchestrator` is read-only and builds sessions from existing evidence bundles.
- No safe persisted DATA_ONLY Full Mesh seed handoff contract was found, so Stage 4 marks handoff as `SKIPPED`.

## Architecture

New service:

- `app/services/proactive_candidate_generation.py`

New Control Center wrapper:

- `app/control_center/proactive_candidate_generation.py`

New API surface:

- `GET /dashboard/api/v2/control/proactive-candidate-generation`
- `POST /dashboard/api/v2/control/proactive-candidate-generation/refresh`
- `GET /dashboard/api/v2/control/proactive-candidate-generation/by-market`
- `GET /dashboard/api/v2/control/proactive-candidate-generation/by-event`
- `GET /dashboard/api/v2/control/proactive-candidate-generation/by-seed`

New migration:

- `app/db/migrations/0136_proactive_candidate_generation.sql`

## Candidate Seed Data Model

The new `proactive_candidate_seeds` table records:

- source event link ids
- targeted revalidation id
- market identity
- side and token when safely resolvable
- revalidation/orderbook/liquidity/spread/payout/movement states
- already-priced-in state
- candidate event scope state
- research-only and permission flags
- mesh handoff state
- blockers, soft warnings, and required-to-pass

Every seed defaults to:

- `research_only = true`
- `execution_allowed = false`
- `paper_allowed = false`
- `shadow_allowed = false`
- `live_allowed = false`

## Generation Policy

Stage 4 consumes only rows where:

- `eligible_for_candidate_generation_later = true`
- `revalidation_state = REVALIDATED`
- market identity is `VERIFIED`
- token verification is `TOKENS_VERIFIED`
- orderbook refresh is `FRESH`
- link type is `DIRECT_LINK` or `LIKELY_LINK`
- market is active
- no token-side conflict exists

Rows that fail policy are represented as blocked research truth when sampled, not as executable candidates.

## YES / NO / SIDE_UNKNOWN Logic

- `direction_for_market = YES` plus token-side clarity creates a YES research seed using `yes_token_id`.
- `direction_for_market = NO` plus token-side clarity creates a NO research seed using `no_token_id`.
- `UNKNOWN`, `MIXED`, `NEUTRAL`, or market-level/token-side-unknown evidence creates `WATCH_ONLY` / `SIDE_UNKNOWN`.
- Token-side conflict blocks the seed.

No side is inferred from weak evidence.

## Already-Priced-In Handling

If `already_priced_in_state = YES`, a seed is downgraded to `WATCH_ONLY` with `EVENT_ALREADY_PRICED_IN`.

If priced-in state is `UNKNOWN` or `NOT_EVALUATED`, the seed remains DATA_ONLY with a soft warning.

## Mesh Handoff Policy

No safe persisted DATA_ONLY Full Mesh seed handoff table was found.

Therefore:

- `mesh_handoff_state = SKIPPED`
- reason: `SAFE_FULL_MESH_DATA_ONLY_HANDOFF_NOT_FOUND_STAGE4_PREP_ONLY`
- no Mesh approval, Edge thesis, score, or execution candidate is fabricated

## Deduplication

Seed ids are deterministic by:

- targeted revalidation id
- seed side

Existing seed rows are updated instead of recreated.

## API Endpoints

The new endpoint returns:

- total seed count
- generated/watch/blocked counts
- YES/NO/SIDE_UNKNOWN counts
- mesh handoff sent/skipped counts
- source events and markets used
- average link confidence
- direction counts
- top generated/watch/blocked seed samples
- latest generation run status

## Integration Surfaces

Read-only metadata was added to:

- Targeted Market Revalidation summary and samples
- Source Event Memory counts
- Market Universe Memory samples
- Paper Actionability items
- Trade Opportunity Score payloads
- Decision Propagation Trace rows
- Source Refresh Orchestrator DATA_ONLY cycle

No scoring formula, paper actionability gate, risk rule, capital rule, exit rule, or lifecycle rule was changed.

## Tests Run

- `.venv\Scripts\python.exe -m pytest tests/test_proactive_candidate_generation.py tests/test_proactive_candidate_generation_policy.py tests/test_proactive_candidate_mesh_handoff.py tests/test_proactive_candidate_generation_integration_surfaces.py -q`
  - `14 skipped`
- `.venv\Scripts\python.exe -m pytest tests/test_targeted_market_revalidation.py tests/test_revalidation_selection_policy.py tests/test_revalidation_refresh_states.py tests/test_revalidation_integration_surfaces.py tests/test_trade_opportunity_scoring.py -q`
  - `5 passed, 10 skipped`
- `.venv\Scripts\python.exe -m pytest tests -q -k "proactive_candidate or candidate_generation or targeted_market_revalidation or revalidation or source_event_memory or market_universe or opportunity_score or paper_actionability or decision_trace"`
  - `38 passed, 34 skipped, 2124 deselected`
- `.venv\Scripts\python.exe -m compileall app tests`
  - passed

Local skips are DB-environment skips where `POLYBOT_DATABASE_URL` is not configured.

## Deployment

- `docker compose build api` passed.
- `docker compose build migrate` passed.
- `docker compose run --rm migrate` passed and applied `0136_proactive_candidate_generation.sql`.
- `docker compose up -d --no-deps api` passed.
- `/healthz` returned `ok`.
- `/runtime/health` returned healthy before verification and `SAFE_STOPPED` after cleanup.

## DATA_ONLY Verification

Completed on 2026-06-18 UTC.

Actions:

1. Triggered Source Event Memory refresh.
2. Triggered Market Universe Memory refresh.
3. Triggered Targeted Market Revalidation refresh.
4. Triggered Proactive Candidate Generation refresh.
5. Posted `SYSTEM ON`.
6. Waited multiple runtime/source-refresh cycles.
7. Verified proactive candidate generation summary and by-seed/by-market/by-event endpoints.
8. Posted `SYSTEM OFF`.

Paper Simulation remained OFF. Full Monitor Run remained diagnostic idle. Shadow and Live remained disabled.

Initial counts:

- proactive candidate seeds: 0
- `fresh_candidate_seeds`: 22
- `market_link_candidates`: 0
- `paper_eligibility_candidates`: 21303
- paper intents/orders/fills/positions: 21 / 12 / 9 / 12
- live orders / positions / shadow orders: 0 / 0 / 0

After manual Stage 4 refresh:

- proactive candidate seeds: 40
- generated: 20
- blocked: 20
- YES: 20
- NO: 0
- SIDE_UNKNOWN: 20
- mesh handoff sent: 0
- mesh handoff skipped: 40

After DATA_ONLY SYSTEM ON cycles and cleanup:

- proactive candidate seeds: 191
- generated: 136
- blocked: 55
- YES: 117
- NO: 19
- SIDE_UNKNOWN: 55
- mesh handoff sent: 0
- mesh handoff skipped: 191
- source events used: 160
- markets used: 9
- average link confidence: 0.8679
- blocked reasons: `ORDERBOOK_NOT_FRESH`, `REVALIDATION_NOT_CANDIDATE_GENERATION_ELIGIBLE`, `REVALIDATION_NOT_CLEAN_PARTIAL`, `CANDIDATE_EVENT_SCOPE_NOT_VERIFIED`, `TOKEN_SIDE_NOT_CANDIDATE_ACTIONABLE`

Final safety counts:

- `fresh_candidate_seeds`: 22 -> 22
- `market_link_candidates`: 0 -> 0
- `paper_eligibility_candidates`: 21303 -> 21326 from the existing DATA_ONLY candidate/no-trade runtime path, not from the Stage 4 seed service
- paper intents/orders/fills/positions: 21 / 12 / 9 / 12 -> unchanged
- live orders / positions / shadow orders: 0 / 0 / 0 -> unchanged

Latest Stage 4 run metadata reported:

- `trading_mutation = false`
- `paper_artifacts_created = false`
- `execution_candidates_created = false`
- `mesh_handoff_policy = SAFE_FULL_MESH_DATA_ONLY_HANDOFF_NOT_FOUND_STAGE4_PREP_ONLY`

## Safety Result

Safety result: GREEN.

Stage 4 is DATA_ONLY and does not create execution candidates, paper intents, paper orders, paper fills, paper positions, live orders, or shadow orders.

The existing runtime's paper eligibility/no-trade path continued to write DATA_ONLY truth rows during SYSTEM ON; Stage 4 did not write to `paper_eligibility_candidates`, `fresh_candidate_seeds`, or `market_link_candidates`.

## Limitations

- Full Mesh handoff is prepared but not sent because no safe persisted DATA_ONLY seed input contract exists yet.
- Stage 4 seeds are not opportunity scores and do not imply Paper Observation execution readiness.
- SIDE_UNKNOWN seeds are watch-only research truth.

## Recommended Stage 5

Full Mesh Deep Inquiry for Proactive Candidate Seeds.

Stage 5 should add a safe DATA_ONLY Mesh handoff contract that consumes `proactive_candidate_seeds` without touching paper/live/shadow execution.
