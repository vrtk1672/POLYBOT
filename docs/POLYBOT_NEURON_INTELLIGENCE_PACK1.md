# POLYBOT Neuron Intelligence Pack 1

## Purpose

Neuron Intelligence Pack 1 converts existing source-backed market evidence into decision-quality neuron evidence. It is observational only and does not create intents, orders, fills, positions, risk approvals, exit readiness, or eligibility.

Pack 1 neurons:

- Rules / Wording Neuron
- Liquidity Neuron
- Fees / Rewards Neuron
- Time Neuron
- News Neuron

## Runtime Contract

SYSTEM OFF blocks Pack 1 execution. A blocked run may record a run summary with `SYSTEM_POWER_OFF`, but no neuron evidence rows are created.

SYSTEM ON allows Pack 1 to run if the StateGovernor permits `RUN_INTELLIGENCE`.

Runtime order:

1. Evidence Refresh
2. Side Evidence
3. Trusted Orderbook Evidence
4. Neuron Intelligence Pack 1
5. Downstream Evidence Recompute
6. Post-Side Risk / Exit Readiness
7. Candidate Eligibility
8. Paper Intent / Execution / Exit if separately allowed

## Evidence Tables

Pack 1 persists:

- `neuron_intelligence_runs`
- `neuron_intelligence_evidence`

Evidence rows include:

- candidate and market identifiers
- neuron name
- source table and source record id
- decision and status
- score and confidence
- score JSON
- evidence JSON
- consumers
- blockers
- human-readable message

## Source Strategy

Rules / Wording consumes `rules_analysis` and `market_rules`.

Liquidity consumes trusted `orderbook_snapshots` linked through `trusted_orderbook_evidence_links`.

Fees / Rewards consumes `fee_snapshots` and orderbook spread cost.

Time consumes `markets_v2`, `market_snapshots_v2`, or `market_snapshots` close/resolution timing.

News consumes `news_impact_scores`. If no source-backed news impact exists, the News Neuron records `UNVERIFIED` with `NO_NEWS_EVIDENCE`; it does not invent news.

## Dashboard

`GET /dashboard/api/v2/neuron-intelligence` returns:

- `mock_data=false`
- latest run truth
- system power
- Rules scores
- Liquidity scores
- Fees scores
- Time scores
- News scores
- recent evidence rows

## Dialogue

`BrainDialogueService.materialize_recent()` materializes Pack 1 evidence into `brain_dialogue_events` using `source_table='neuron_intelligence_evidence'`.

Dialogue uses the original neuron component names and cites each source evidence row. Dashboard reads do not create duplicate dialogue events because existing dialogue uniqueness applies to source table, source record id, and event type.

## Safety

Pack 1:

- does not enable live or shadow trading
- does not create paper artifacts
- does not create real orders
- does not mutate risk, exit, eligibility, paper execution, capital, or PnL
- keeps missing source evidence blocked or unverified
