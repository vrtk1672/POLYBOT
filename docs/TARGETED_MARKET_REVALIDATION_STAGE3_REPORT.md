# Targeted Market Revalidation Stage 3 Report

## Purpose

Stage 3 turns strong Source Event Memory recall into current market truth. It is DATA_ONLY and does not create execution candidates, paper intents, paper orders, fills, positions, shadow orders, live orders, or real orders.

## Money Machine Fit

The flow now supports:

source event -> event-to-market recall -> targeted market revalidation -> verified market/orderbook/liquidity/spread/payout/movement truth -> future proactive candidate generation.

Stage 3 stops at fresh market truth. Stage 4 is still required before proactive candidates are created.

## Existing Refresh / Revalidation Audit

- Existing eligible recall source: `event_to_market_recall`.
- Existing market identity source: `market_universe_memory`.
- Existing orderbook truth: `orderbook_snapshots`.
- Existing payout/odds truth: `payout_odds_evaluations`.
- Existing movement/signal truth: `market_technical_signals`, `orderbook_signals`.
- Existing source refresh hook: `SourceRefreshOrchestrator`.
- No prior targeted revalidation table existed.

## Architecture

Implemented `TargetedMarketRevalidationService` as a bounded DATA_ONLY service.

It:

- selects only `DIRECT_LINK` and high-confidence `LIKELY_LINK` rows with `candidate_actionability_hint = REVALIDATION_ELIGIBLE`;
- skips weak/context/no-link/watch-only/low-confidence rows;
- loads market memory;
- verifies identity and tokens;
- reads latest local orderbook, payout, movement, and signal truth;
- classifies already-priced-in state conservatively;
- writes `targeted_market_revalidations`;
- writes refresh-run audit rows;
- exposes summary, by-market, and by-event endpoints;
- integrates read-only fields into source event memory, market memory, opportunity score, paper actionability, and decision trace.

## Selection Policy

Eligible:

- `DIRECT_LINK` with confidence >= `0.75`.
- `LIKELY_LINK` with confidence >= `0.70`.
- `candidate_actionability_hint = REVALIDATION_ELIGIBLE`.

Skipped by default:

- `WEAK_LINK`
- `CONTEXT_ONLY`
- `NO_LINK`
- `WATCH_ONLY`
- `BLOCKED_BY_LOW_CONFIDENCE`
- `BLOCKED_BY_TOKEN_SIDE_UNKNOWN`
- `BLOCKED_BY_CONFLICT`

Token-side unknown may support market-level revalidation metadata but is not candidate-actionable.

## Refresh States

Stage 3 records:

- market identity state
- token verification state
- token-side resolution state
- metadata refresh state
- orderbook refresh state
- liquidity state
- spread state
- payout/odds state
- movement state
- signal state
- candidate event scope state
- already-priced-in state
- candidate-generation-later eligibility and blockers

No missing value is fabricated. Missing or stale inputs remain `UNKNOWN`, `MISSING`, `STALE`, or `FAILED`.

## Deduplication / Rate Limiting

Rows are deduplicated by recall id and hourly bucket. The service skips recently revalidated links unless `force=true`.

The orchestrator hook uses a bounded limit of 20 links and a small skipped sample. Manual refresh defaults to a bounded limit.

## API Endpoints

Added:

- `GET /dashboard/api/v2/control/targeted-market-revalidation`
- `POST /dashboard/api/v2/control/targeted-market-revalidation/refresh`
- `GET /dashboard/api/v2/control/targeted-market-revalidation/by-market?market_id=...`
- `GET /dashboard/api/v2/control/targeted-market-revalidation/by-event?source_event_id=...`

Changed read-only surfaces:

- `/source-event-memory`
- `/market-universe-memory`
- `/trade-opportunity-score`
- `/paper-actionability`
- `/decision-propagation-trace`

## Verification Result

Deployment:

- `docker compose build api`: passed
- `docker compose build migrate`: passed
- `docker compose run --rm migrate`: applied `0135_targeted_market_revalidation.sql`
- `docker compose up -d --no-deps api`: passed

Health:

- `/healthz`: OK
- `/runtime/health`: active server verified

Controlled DATA_ONLY verification:

- `POST SYSTEM ON`: accepted, DATA_ONLY, Paper Simulation OFF
- waited for supervisor/source-refresh cycles
- `POST SYSTEM OFF`: accepted
- final runtime: STOPPED
- final system power: OFF
- final supervisor: STOPPED

## Counts

Final targeted revalidation endpoint:

- eligible links seen: 200
- total revalidation rows: 120
- revalidated: 20
- partial: 70
- skipped: 30
- failed: 0
- markets refreshed: 1
- orderbook fresh: 20
- orderbook stale: 70
- orderbook failed: 0
- tokens verified: 90
- token mismatch: 0
- liquidity medium: 90
- spread medium: 90
- payout odds available: 90
- payout odds missing: 30
- movement unknown: 120
- already priced in unknown: 120
- candidate-generation-later eligible: 20

Skipped reasons:

- `WATCH_ONLY_NOT_REVALIDATED_BY_STAGE3_POLICY`: 26
- `LIKELY_LINK_BELOW_REVALIDATION_THRESHOLD`: 4

## Examples

Revalidated:

- market_id: `691547`
- source_event_id: `source_event_872e35f36ea8582ff5123c2e`
- link: `LIKELY_LINK`, confidence `0.87`
- orderbook: `FRESH`
- liquidity: `MEDIUM`
- spread: `MEDIUM`
- payout/odds: `AVAILABLE`
- already priced in: `UNKNOWN`
- candidate generation later: `true`

Partial:

- market_id: `691547`
- link: `DIRECT_LINK`, confidence `1.0`
- orderbook: `STALE`
- blockers: token/side not candidate-actionable, orderbook not fresh, candidate event scope not verified

Skipped:

- market_id: `598936`
- link: `LIKELY_LINK`, confidence `0.6784`
- reason: `WATCH_ONLY_NOT_REVALIDATED_BY_STAGE3_POLICY`

## Safety Result

- Paper Simulation remained OFF.
- Shadow remained disabled.
- Live remained disabled.
- No execution candidates were created.
- No paper artifacts were created.
- No live/shadow artifacts were created.
- No DB destructive action was used.
- Risk, Capital, Exit, and Lifecycle thresholds were not changed.

## Limitations

- Stage 3 reads local orderbook/signal truth; it does not force external orderbook fetches outside existing runtime refresh paths.
- Movement and already-priced-in remained `UNKNOWN` for the final dataset because the available movement evidence was insufficient.
- Candidate-generation-later is only a DATA_ONLY readiness marker, not an execution approval.

## Recommended Stage 4

Proactive Candidate Generation from Revalidated Markets.
