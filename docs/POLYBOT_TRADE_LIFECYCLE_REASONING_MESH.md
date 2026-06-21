# POLYBOT Trade Lifecycle Reasoning Mesh

Date: 2026-06-03
Executor: Codex
Security governance: YELLOW_ACCEPTED_BY_OPERATOR
Task mode: CONTROLLED_RUNTIME_FEATURE + MESH_REASONING + TRADE_LIFECYCLE_PLANNING
Risk: VERY HIGH

## Purpose

The Trade Lifecycle Reasoning Mesh creates a source-backed lifecycle plan for a fresh seed, paper candidate, paper intent, or open paper position. It is an observational reasoning layer only.

Core law:

```text
Mesh decides.
Pipeline executes.
```

The lifecycle mesh does not create paper intents, paper orders, paper fills, paper positions, paper closes, live orders, or balance mutations. It aggregates existing brain and source records into one plan that the Coordinator can inspect.

## Supported Subjects

- FRESH_SEED
- PAPER_CANDIDATE
- PAPER_INTENT
- PAPER_POSITION

## Plan Model

Each lifecycle plan records:

- strategy_type
- plan_status
- decision_class
- economic_thesis
- entry_thesis
- exit_thesis
- hold_to_resolution_thesis
- invalidation_rules_json
- capital_plan_json
- monitoring_plan_json
- risk_summary_json
- liquidity_summary_json
- payout_summary_json
- exit_hold_summary_json
- capital_efficiency_summary_json
- same_market_summary_json
- coordinator_judgment_json
- missing_inputs_json
- source_refs_json

The plan is derived from repository truth. Missing sources are explicitly recorded instead of inferred.

## Strategy Types

Allowed strategy types:

- REPRICING_CANDIDATE
- HOLD_TO_RESOLUTION_CANDIDATE
- EXIT_NOW_REVIEW
- HOLD_REVIEW
- CAPITAL_EFFICIENCY_PLAY
- WATCH_ONLY
- NO_TRADE
- INSUFFICIENT_DATA
- RISK_BLOCKED
- EXIT_BLOCKED
- CAPITAL_BLOCKED
- SAME_MARKET_BLOCKED
- UNKNOWN

Blocked source records dominate strategy classification:

- Same-market guard BLOCK -> SAME_MARKET_BLOCKED
- Risk BLOCK -> RISK_BLOCKED
- Exit plan BLOCKED -> EXIT_BLOCKED
- Capital efficiency CAPITAL_BLOCK -> CAPITAL_BLOCKED

The mesh does not invent strategy. When complete rationale is unavailable, it emits WATCH_ONLY or INSUFFICIENT_DATA with missing inputs.

## Plan Status

Allowed statuses:

- COMPLETE
- PARTIAL
- WATCH
- NO_TRADE
- BLOCKED
- INSUFFICIENT_DATA

COMPLETE requires the core source set plus no critical missing lifecycle inputs. Missing news, whale, memory, time-to-resolution, rules/wording, same-market guard, position watchdog, or orderbook truth prevents a complete plan.

## Decision Classes

Allowed decision classes:

- PAPER_CANDIDATE_REVIEW
- PAPER_INTENT_READY_CONTEXT
- HOLD_REVIEW
- EXIT_REVIEW
- NO_TRADE
- WATCH
- BLOCKED
- INSUFFICIENT_DATA

Decision classes are context for the Coordinator. They do not execute trades or exits.

## Mesh Contributions

Every plan stores available brain/source contributions in `trade_lifecycle_brain_contributions`.

Supported contribution sources include:

- Payout/Odds
- Exit/Hold
- Capital Efficiency
- Same-Market Guard
- Risk
- Exit Foundation
- Capital Brain
- Orderbook/Liquidity
- Position Watchdog
- Rules/Wording
- News/AI Context
- Whale
- Memory
- Coordinator

If a source is absent, the plan records a missing input and does not fabricate a stance.

## Source Rules

Use source-backed data only:

- Payout/Odds from `payout_odds_evaluations`
- Exit/Hold from `exit_hold_evaluations`
- Capital Efficiency from `capital_efficiency_evaluations`
- Same-market coherence from `same_market_side_guard_decisions`
- Risk from `risk_decisions`
- Exit Foundation from `exit_plans`
- Capital Brain from `capital_brain_evaluations`
- Coordinator from `mesh_coordinator_decisions`
- Liquidity from `orderbook_snapshots`
- Position monitoring from `position_awareness`, `position_reactions`, and watchdog traces
- Rules/wording from `rules_analysis` and `market_rules`
- News from `news_impact_scores`
- Whale from `whale_events`
- Memory from `market_memory_v2` or compatible market memory rows

Fair probability, edge, confidence, and thesis are not generated when no source-backed record exists.

## API

Dashboard truth:

```text
GET /dashboard/api/v2/trade-lifecycle
GET /dashboard/api/v2/trade-lifecycle/{plan_id}
```

Builder endpoint:

```text
POST /trade-lifecycle/build
```

The build endpoint supports bounded construction by `subject_type`, `limit`, and `dry_run`. It writes only lifecycle plan tables when `dry_run=false`.

## Integrations

Paper forensics exposes lifecycle plan fields for traced paper positions:

- strategy type
- plan status
- decision class
- economic thesis
- entry thesis
- exit thesis
- hold thesis
- capital plan
- monitoring plan
- invalidation rules
- coordinator judgment
- missing inputs
- brain contributions

Capital Brain, Exit Foundation, and Mesh Coordinator dashboard/details expose lifecycle visibility as observational input. The lifecycle plan does not override those services.

Brain Dialogue emits source-backed lifecycle events, including blocked plans, partial plans, hold/exit review plans, and missing-input explanations.

## Safety Boundary

The lifecycle mesh may create or update:

- trade_lifecycle_plans
- trade_lifecycle_plan_sources
- trade_lifecycle_brain_contributions
- brain_dialogue_events for source-backed lifecycle dialogue

The lifecycle mesh must not mutate:

- paper_intents
- paper_orders
- paper_fills
- paper_positions
- paper_position_closes
- paper_capital_ledger
- paper_accounts
- live_orders
- orders_v2
- fills_v2
- canonical positions

## Rollback

Disable use by not calling `TradeLifecycleService` and hiding the dashboard routes. To remove persisted derived records, delete rows from lifecycle tables only:

```sql
DELETE FROM trade_lifecycle_brain_contributions;
DELETE FROM trade_lifecycle_plan_sources;
DELETE FROM trade_lifecycle_plans;
```

Do not alter paper trading, capital, live, or canonical execution tables during rollback.

