# V2.10 Context Brain + Capital Brain

## Purpose

V2.10 connects world understanding with capital awareness while keeping them separate.

Context Brain asks: did something happen that changes the true probability of a market?

Capital Brain asks: could capital be reserved for this kind of setup, from which bucket, and under what constraints?

This phase is analysis and recommendation infrastructure only. It does not create orders, order intents, exits, opportunity scores, strategy routes, risk approvals, or live trading behavior.

## Architecture

Package: `app/brains/`

- `contracts.py` defines Context Brain, Capital Brain, and combined snapshot contracts.
- `context_input_builder.py` gathers news, social, whale, technical, rules, and market memory truth.
- `capital_input_builder.py` gathers paper capital snapshot data and market memory when available, or explicit safe test payloads.
- `context_signal_scorer.py` applies deterministic context-shift scoring.
- `capital_recommendation_builder.py` applies deterministic capital constraints.
- `context_brain.py` ensures AI summaries cannot override deterministic risks.
- `capital_brain.py` returns recommendation-only capital outputs.
- `service.py` runs, persists, and publishes redacted events.

## DB Tables

Migration: `app/db/migrations/0048_v2_10_context_capital_brains.sql`

Tables:

- `context_brain_runs`
- `context_brain_outputs`
- `capital_brain_runs`
- `capital_brain_outputs`

These store structured summaries and references only. They do not duplicate raw neuron data.

## API Routes

Prefix: `/brains`

- `GET /brains/health`
- `GET /brains/context/market/{market_id}`
- `GET /brains/capital/market/{market_id}`
- `GET /brains/market/{market_id}`
- `GET /brains/context/recent`
- `GET /brains/capital/recent`
- `GET /brains/blocked/recent`
- `POST /brains/context/analyze`
- `POST /brains/capital/analyze`
- `POST /brains/analyze`

Analysis endpoints are intelligence-only. `dry_run=true` returns computed output without writing.

## Event Types

- `context_brain.run.started`
- `context_brain.output.created`
- `context_brain.insufficient_data`
- `capital_brain.run.started`
- `capital_brain.output.created`
- `capital_brain.blocked`
- `capital_brain.insufficient_data`
- `brain.snapshot.created`

Events are redacted and use run IDs, market IDs, confidence, block status, and insufficient-data flags.

## Context Brain Logic

Context Brain consumes:

- V2.4 news impact signals
- V2.5 rules/risk memory
- V2.6 social/hype signals
- V2.7 whale signals weighted by whale memory
- V2.8 technical truth
- V2.9 market memory
- optional AI summaries

It computes:

- `context_shift`
- `direction`
- `strength`
- `confidence`
- `already_priced_in_score`
- `ttl_seconds`
- `urgency_score`
- `risk_score`
- supporting and contradicting signals
- insufficient-data reasons

It can say:

- no real shift
- insufficient data
- conflicting or weak signals
- shift exists but already priced in
- shift exists but wording/rules risk remains high

AI can summarize context, but it cannot override deterministic risk flags.

## Capital Brain Logic

Capital Brain consumes:

- balance and available capital
- locked capital and open exposure
- engine budgets
- risk limits
- capital recycling signal
- slippage and family memory

It computes:

- `capital_allowed`
- `block_reason`
- `max_position_size_usd`
- `risk_budget_usd`
- `capital_bucket`
- `cash_reserve_after_usd`
- `engine_budget_remaining_usd`
- `allocation_confidence`
- `allocation_reason`

It blocks for:

- missing available capital
- missing balance
- low cash reserve
- exhausted engine budget
- excessive open exposure
- unsafe slippage memory
- insufficient data

Capital Brain never mutates balances.

## Interesting vs Worth Money

`BrainCombinedSnapshot` makes the separation explicit:

- `interesting`: Context Brain sees a context shift with confidence.
- `worth_money`: interesting plus Capital Brain says capital could be reserved.
- `ready_for_opportunity_cortex`: data is sufficient for future V2.11 review.

Interesting does not automatically become worth money.

## Dashboard Fields

The dashboard overview includes `brains`:

- `brain_status`
- `context_runs_today`
- `capital_runs_today`
- `latest_context_shift`
- `latest_capital_allowed`
- `insufficient_data_count`
- `capital_blocked_count`
- `top_context_shifts`
- `top_capital_blocks`
- `average_context_confidence`
- `average_allocation_confidence`
- `common_context_risks`
- `common_capital_block_reasons`
- `latest_brain_update`
- `errors`

The panel is DB-backed only. Empty data is reported honestly.

## Safety Boundaries

V2.10 cannot:

- create orders
- create order intents
- create exits
- mutate balances
- approve risk
- route strategies
- create opportunity scores
- enable live trading

Brain analysis checks the State Governor with `RuntimeAction.RUN_INTELLIGENCE`.

## Tests

Added V2.10 tests for:

- context shift/no shift
- insufficient context data
- already-priced-in downgrade
- rules risk exposure
- whale weighting by memory, not size
- social noise penalty
- AI risk override guard
- capital reserve, budget, exposure, slippage blocks
- no balance mutation
- combined snapshot separation
- service/API/safety paths, DB-backed when Postgres is available

## Known Limitations

- DB-backed tests and runtime smoke could not be completed in this session because local Postgres/Docker was unavailable.
- Capital data uses existing paper capital truth or explicit safe test payloads. Sparse capital state is reported as insufficient data.
- V2.10 does not implement Opportunity Cortex or Capital Allocator V2.

## Next Recommended Phase

V2.11 Opportunity Cortex should start only after DB-backed V2.10 migration, API, and runtime verification complete.
