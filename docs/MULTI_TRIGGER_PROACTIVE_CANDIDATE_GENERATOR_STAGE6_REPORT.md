# POLYBOT Money Machine Core - Stage 6 Report

## Purpose

Stage 6 upgrades proactive candidate generation from event-recall-only seeds into a DATA_ONLY multi-trigger generator. It detects real market triggers, maps them to Market Universe Memory, validates identity/token/priority context, generates research-only proactive seeds, and lets the existing Stage 5 / 5.5 DATA_ONLY Mesh path review clean seeds.

## Money Machine Fit

This stage expands opportunity hunting beyond news/event recall. POLYBOT can now form research hypotheses from market movement, payout/odds discrepancy, signal quality, and framework-ready trigger families without creating execution candidates or paper/live/shadow artifacts.

## Existing Generator Audit

- Stage 4 canonical seed table: `proactive_candidate_seeds`.
- Stage 5 inquiry contract: `proactive_seed_mesh_inquiries` / `proactive_seed_mesh_results`.
- Stage 5.5 DATA_ONLY adapter: `proactive_seed_mesh_adapter_payloads`.
- Existing trigger evidence found:
  - `market_technical_signals`
  - `orderbook_signals`
  - `payout_odds_evaluations`
  - `whale_market_scores`
  - `signal_quality_evaluations` + `neuron_signals`
  - `market_universe_memory`
  - `research_priority_watchlist`
- `neuron_signals` uses `raw_direction`; it does not have `side` or `token_id`.
- No qualifying production `ORDERBOOK_PRESSURE` or whale/wallet triggers were present during verification.

## Architecture

- New service: `MultiTriggerProactiveCandidateGeneratorService`.
- New control wrapper: `MultiTriggerCandidateGenerationControlService`.
- New table: `multi_trigger_candidate_triggers`.
- New run ledger: `multi_trigger_candidate_generation_runs`.
- `proactive_candidate_seeds` extended with trigger lineage fields.
- Source-refresh orchestrator runs Stage 6 after research priority refresh and before seed Mesh inquiry.

## Trigger Families

Implemented:

- `MARKET_MOVEMENT`
- `PAYOUT_DISCREPANCY`
- `ORDERBOOK_PRESSURE`
- `WHALE`
- `EVENT_WINDOW`
- `SIGNAL_QUALITY`

Framework constants include the broader Stage 6 seed types for future extension.

## Data Model

Canonical trigger records include:

- trigger id/type
- market memory/market/condition ids
- optional source evidence ids
- side hint/confidence
- trigger strength/confidence/score
- research priority
- guardrail blockers/watch reasons
- seed generation state
- proactive seed id
- metadata/source row lineage

## Trigger Score

`trigger_score = 45*trigger_strength + 35*trigger_confidence + 20*(research_priority_score/100)`, clamped to `0-100`.

Movement strength uses the strongest of scaled price move, momentum score, and trend strength. Payout confidence uses fair/EV evidence when available, or existing risk/reward evidence when no fair value is present. No fair value is invented.

## Seed Policy

Generated YES/NO seed requires:

- active market
- `TOKENS_VERIFIED`
- HIGH/MEDIUM research priority
- trigger score >= 60
- side YES/NO
- side confidence >= 0.60
- side token present

WATCH_ONLY/SIDE_UNKNOWN seed is created when the trigger is interesting but side is unclear. Low confidence, inactive markets, token mismatch, missing side token, or low priority block/skips.

All seeds remain:

- `research_only=true`
- `execution_allowed=false`
- `paper_allowed=false`
- `shadow_allowed=false`
- `live_allowed=false`

## Mesh Adapter Handoff

Stage 6 seeds are persisted into `proactive_candidate_seeds`. Existing Stage 5 seed inquiry and Stage 5.5 adapter consume clean generated YES/NO seeds through DATA_ONLY rules. Stage 6 itself does not call execution paths.

## API

Added:

- `GET /dashboard/api/v2/control/multi-trigger-candidate-generation`
- `POST /dashboard/api/v2/control/multi-trigger-candidate-generation/refresh`
- `GET /dashboard/api/v2/control/multi-trigger-candidate-generation/by-market`
- `GET /dashboard/api/v2/control/multi-trigger-candidate-generation/by-trigger`

Updated surfaces:

- proactive candidate generation shows trigger metadata and seed generation source
- research priority watchlist includes multi-trigger fields
- opportunity score includes `multi_trigger_id`, `trigger_type`, `trigger_score`, `seed_generation_source`
- decision propagation trace includes trigger lineage fields

## Verification Counts

Final Stage 6 endpoint:

- total triggers detected: 48
- eligible triggers: 32
- watch-only triggers: 16
- blocked triggers: 0
- duplicate triggers: 0
- generated YES/NO seeds: 32
- YES seeds: 16
- NO seeds: 16
- SIDE_UNKNOWN/WATCH seeds: 22

Triggers by type:

- `MARKET_MOVEMENT`: 16
- `PAYOUT_DISCREPANCY`: 16
- `SIGNAL_QUALITY`: 16

Seeds by trigger type:

- `MARKET_MOVEMENT`: 19
- `PAYOUT_DISCREPANCY`: 19
- `SIGNAL_QUALITY`: 16

Mesh path after verification:

- seed Mesh inquiry rows: 483
- adapter payload rows: 135
- adapter processed: 170
- `MESH_DATA_ONLY_COMPLETED`: 41
- adapter partial: 46
- adapter failed: 0
- Edge supported: 87
- Paper Observation classification: 34
- Full Paper ready: 0

## Examples

- Market movement trigger: market `597967`, side `NO`, score `97.28`, seed `multi_trigger_seed_8b83eac8bfa5927f00cb966ae02be4`.
- Payout discrepancy trigger: market `610236`, side `YES`, score `85.55`, seed `multi_trigger_seed_64ac56d26984260cadad1bc0f70c04`.
- Signal-quality watch trigger: market `691547`, side `SIDE_UNKNOWN`, score `85.9`, watch reason `SIDE_UNKNOWN_NOT_ACTIONABLE`.
- Orderbook pressure: no qualifying production evidence during verification.
- Whale/wallet: no qualifying production evidence during verification.

## Tests

- Focused: `18 passed`
- Related: `13 passed, 7 skipped`
- Broad: `90 passed, 18 skipped, 2162 deselected`
- Compile: `python -m compileall app tests` passed.

## Deployment

- `docker compose build api`: passed.
- `docker compose build migrate`: passed.
- `docker compose run --rm migrate`: applied `0140_multi_trigger_candidate_generation.sql`.
- `docker compose up -d --no-deps api`: passed.
- Active server verified with `/healthz`.

## DATA_ONLY Verification

Actions:

1. Triggered market universe refresh.
2. Triggered source event refresh.
3. Triggered targeted market revalidation refresh.
4. Triggered research priority watchlist refresh.
5. Triggered multi-trigger generation refresh.
6. Triggered proactive seed Mesh inquiry refresh.
7. Triggered DATA_ONLY Mesh adapter run.
8. POSTed SYSTEM ON.
9. Waited three DATA_ONLY supervisor cycles.
10. POSTed SYSTEM OFF cleanup.

Final runtime health:

- overall: `SAFE_STOPPED`
- mode: `DATA_ONLY`
- system power: `OFF`
- supervisor: `REGISTERED_NOT_RUNNING`
- paper runtime: `STOPPED`

## Artifact Counts

Before:

- multi-trigger rows: 0
- proactive candidate seeds: 500
- seed Mesh inquiries: 360
- adapter payloads: 65
- execution candidate `fresh_candidate_seeds`: 22
- `market_link_candidates`: 0
- paper intents/orders/fills/positions: 21 / 12 / 9 / 12
- live orders / positions / shadow orders: 0 / 0 / 0

After:

- multi-trigger rows: 48
- proactive candidate seeds: 677
- seed Mesh inquiries: 483
- adapter payloads: 135
- execution candidate `fresh_candidate_seeds`: 22
- `market_link_candidates`: 0
- paper intents/orders/fills/positions: 21 / 12 / 9 / 12
- live orders / positions / shadow orders: 0 / 0 / 0

## Safety Result

GREEN.

No paper, live, shadow, real order, execution candidate, or capital mutation was created. Paper Simulation remained OFF. Stage 6 only wrote DATA_ONLY trigger rows and research seed/adapter metadata.

## Limitations

- No qualifying orderbook-pressure production triggers appeared in the verification window.
- No qualifying whale/wallet production triggers appeared in the verification window.
- Cross-market trigger logic remains unimplemented because no safe existing relation data was found.
- Stage 6 emits research hypotheses; it does not approve Paper Observation execution.

## Recommended Next Stage

If enough Mesh-reviewed Paper Observation classifications accumulate, run Paper Observation Policy Review. Otherwise, expand universe/trigger coverage, especially orderbook pressure and whale/wallet directional evidence.
