# V2.11 Opportunity Cortex

## Purpose

V2.11 adds a scoring-only Opportunity Cortex. It answers whether a measurable opportunity candidate exists by combining Context Brain, Capital Brain, technical market truth, market memory, news, rules, social, whale, fee, liquidity, and data-completeness inputs.

It does not route strategies, approve risk, allocate capital, create order intents, create orders, create exits, or mutate balances.

## Architecture

- `app/opportunity/contracts.py`: typed opportunity inputs, scores, risk flags, signal inputs, and run result contracts.
- `app/opportunity/signal_input_builder.py`: gathers latest DB truth or explicit smoke/test manual input.
- `app/opportunity/opportunity_scorer.py`: deterministic scoring formula and reproducibility hash.
- `app/opportunity/risk_flag_builder.py`: hard and soft risk flags.
- `app/opportunity/candidate_engine_suggester.py`: candidate engine suggestions only.
- `app/opportunity/no_trade_reason_builder.py`: scoring-time no-trade reasons.
- `app/opportunity/service.py`: persistence, events, runtime-mode guard.
- `app/api/opportunity_routes.py`: read APIs plus safe scoring endpoint.

## DB Tables

Migration: `app/db/migrations/0049_v2_11_opportunity_cortex.sql`

- `opportunity_runs`: scoring run metadata.
- `opportunity_scores_v2`: final explainable opportunity score.
- `opportunity_signal_inputs`: reproducible inputs, weights, and contributions.
- `opportunity_risk_flags`: explicit risk flags and hard blocks.

These tables summarize scoring truth. They do not duplicate raw source truth and do not represent execution.

## API Routes

- `GET /opportunities/health`
- `GET /opportunities/market/{market_id}`
- `GET /opportunities/recent`
- `GET /opportunities/top`
- `GET /opportunities/blocked/recent`
- `GET /opportunities/risk-flags/recent`
- `GET /opportunities/run/{run_id}`
- `POST /opportunities/score`

`POST /opportunities/score` is intelligence-only. `dry_run=true` returns a score without writing.

## Event Types

- `opportunity.run.started`
- `opportunity.score.created`
- `opportunity.blocked`
- `opportunity.watchlist.created`
- `opportunity.high_score.created`
- `opportunity.insufficient_data`

Payloads are redacted and contain IDs, bands, scores, and summary fields only.

## Scoring Formula

Positive components:

- edge
- confidence
- trigger strength
- repricing potential
- time efficiency
- liquidity quality
- exit probability
- capital recycling speed
- convexity
- balance fit
- fee/reward advantage

Negative components:

- risk penalty
- slippage penalty
- lockup penalty
- correlation risk
- trap risk
- wording risk
- adverse selection risk
- already priced-in score

Hard blocks force `score_band=BLOCKED` and `opportunity_score=0`.

## Score Bands

- `BLOCKED`
- `LOW`
- `WATCHLIST`
- `STRONG`
- `HIGH_CONVICTION`

`HIGH_CONVICTION` requires strong score and confidence. It still does not approve trading.

## Risk Logic

Hard blocks include:

- capital not allowed
- missing bid/ask
- low depth
- poor exit quality
- missing exit liquidity
- technical blocked

Soft penalties include:

- missing data
- high wording risk below hard-block threshold
- wide spread
- high slippage
- already priced-in signal
- high friction
- AI risk boundary markers

High scores cannot override hard blocks.

## No-Trade Reasons

V2.11 produces no-trade reasons as score output only. It does not implement full V2.17 No-Trade Intelligence.

Common reasons:

- missing_data
- bad_liquidity
- missing_bid_ask
- wide_spread
- poor_exit_quality
- high_wording_risk
- already_priced_in
- capital_not_allowed
- low_context_confidence
- high_slippage
- weak_trigger

## Candidate Engine Suggestions

Candidate engines are suggestions for future V2.12 only:

- `SAFE`
- `STRIKE`
- `CONVEX`
- `MAKER`
- `HUNT`
- `NO_TRADE`

V2.11 never routes, executes, or chooses a final strategy.

## Reproducibility

Every score stores:

- component values
- weights
- contributions
- risk flags
- no-trade reasons
- candidate engine suggestions
- explanation
- `reproducibility_hash`

The hash is deterministic for identical score inputs and flags.

## Insufficient Data

Missing context, capital, technical truth, or market memory becomes explicit `insufficient_data`. Missing data lowers score and confidence. It is never hidden or replaced with fake values.

## Dashboard Fields

The dashboard overview now includes DB-backed `opportunities` truth:

- opportunity_status
- runs_today
- scores_today
- blocked_today
- watchlist_today
- high_score_today
- latest_score_ts
- top_opportunities
- recent_blocked_opportunities
- common_risk_flags
- average_score
- average_confidence
- insufficient_data_count
- top_candidate_engines
- errors

No fake data is emitted.

## Safety Boundaries

- Opportunity Cortex cannot create orders.
- Opportunity Cortex cannot create order intents.
- Opportunity Cortex cannot create exits.
- Opportunity Cortex cannot mutate balances.
- Runtime State Governor is respected.
- `KILL` blocks scoring.
- `DATA_ONLY` allows scoring but blocks orders.
- Candidate engines are suggestions only.
- AI context cannot override deterministic risk flags.

## Testing

Coverage includes:

- missing data
- wording risk
- bad liquidity
- missing bid/ask
- poor exit quality
- good trigger
- priced-in penalty
- high slippage
- capital blocked
- memory confidence
- whale/social usefulness
- reward pool not overriding liquidity blocks
- stable reproducibility hash
- service persistence
- API routes
- safety invariants

## Known Limitations

- Historical source sparsity can produce insufficient-data outputs honestly.
- V2.11 does not calibrate score weights from outcomes yet.
- Candidate engines remain suggestions until V2.12.
- Full no-trade learning remains V2.17.

## Future Phases

Next recommended phase: V2.12 Strategy Router + Engines.

