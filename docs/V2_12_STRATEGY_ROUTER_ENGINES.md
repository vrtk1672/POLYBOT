# V2.12 Strategy Router + Engines

## Purpose

V2.12 adds a non-executing Strategy Router and first-class strategy engines. It answers which engine contract best fits an Opportunity Cortex score after independent engine validation.

It does not place orders, create order intents, create exit intents, mutate balances, reserve capital, approve risk, or enable live trading.

## Architecture

- `app/strategy/contracts.py`: route input, engine contract, engine decision, rejection, route, and run result contracts.
- `app/strategy/router.py`: evaluates every engine and selects exactly one route.
- `app/strategy/engine_contract_builder.py`: builds full non-executable engine contracts.
- `app/strategy/engine_rejection_builder.py`: normalizes engine rejection records.
- `app/strategy/engine_cooldown_manager.py`: derives cooldown records from rejection clusters.
- `app/strategy/engines/*`: SAFE, STRIKE, CONVEX, MAKER, HUNT, MOONSHOT_BASKET, REINVEST, and NO_TRADE engines.
- `app/strategy/service.py`: DB input loading, runtime guard, persistence, and event publication.
- `app/api/strategy_routes.py`: read APIs plus safe routing endpoint.

## DB Tables

Migration: `app/db/migrations/0050_v2_12_strategy_router_engines.sql`

- `strategy_route_runs`: Strategy Router run metadata.
- `strategy_routes_v2`: selected route and full engine contract.
- `engine_decisions`: every engine evaluation for every run.
- `engine_rejections`: rejection reasons for ineligible engines.
- `engine_cooldowns`: active and historical cooldown states.

These tables store strategy contracts only. They are not execution tables.

## API Routes

- `GET /strategy/health`
- `GET /strategy/market/{market_id}`
- `GET /strategy/recent`
- `GET /strategy/engines`
- `GET /strategy/rejections/recent`
- `GET /strategy/cooldowns`
- `GET /strategy/run/{run_id}`
- `POST /strategy/route`

`POST /strategy/route` supports `dry_run=true` and optional manual smoke input. It is strategy-only and never writes orders or mutates capital.

## Event Types

- `strategy.route.run.started`
- `strategy.route.created`
- `strategy.route.no_trade`
- `strategy.engine.decision.created`
- `strategy.engine.rejected`
- `strategy.engine.cooldown.created`
- `strategy.route.insufficient_data`

Payloads are redacted and contain run IDs, market IDs, selected engine, status, and summary fields only.

## Router Logic

The router:

- Loads the latest V2.11 opportunity score unless manual smoke input is provided.
- Evaluates every engine independently.
- Persists every engine decision and rejection.
- Selects exactly one route.
- Forces `NO_TRADE` or `BLOCKED` when hard opportunity blocks exist.
- Marks missing source truth as `INSUFFICIENT_DATA`.
- Uses V2.11 candidate engines as suggestions only.
- Stores a deterministic reproducibility hash.

## Engine Rules

SAFE requires high confidence, low wording risk, strong liquidity, clear exit, and capital allowed.

STRIKE requires context trigger, trigger strength, repricing potential, urgency, exit quality, and not already priced in.

CONVEX requires asymmetric upside, defined downside, acceptable small-size liquidity, and manageable wording/trap risk.

MAKER requires orderbook truth, depth, liquidity quality, reward/spread usefulness, and low adverse selection.

HUNT requires explicit `hunt_approval`, high urgency, strong trigger, high repricing potential, strict exit viability, and capital allowed. Without approval it rejects with `hunt_requires_governor_approval`.

MOONSHOT_BASKET requires extreme convexity, small basket sizing, minimum liquidity, strict max loss per candidate, and no averaging down.

REINVEST is metadata-only until V2.13. It rejects with `reinvest_requires_v2_13_profit_pocket` and never moves or reserves funds.

NO_TRADE is always valid and is selected for hard blocks, insufficient data, capital not allowed, or all engines rejected.

## Engine Contracts

Every non-`NO_TRADE` selected route includes:

- market ID and side
- engine
- entry price max
- target exit
- partial take profit
- stop loss
- max position size
- max loss
- max hold minutes
- entry mode
- exit mode
- execution mode `CONTRACT_ONLY`
- entry conditions
- exit conditions
- risk limits
- position sizing rules
- allowed families
- forbidden conditions
- cooldown triggers
- reason

These are future contracts for V2.13+ through V2.16, not orders or intents.

## Rejection Logic

Each engine returns either an eligible decision with a contract or an ineligible decision with a rejection reason. Rejections are persisted and exposed through API/dashboard truth.

## Cooldown Logic

The cooldown manager can create a cooldown when a route produces clustered hard engine rejections. Cooldowns are informational strategy-state records and do not modify runtime mode or trading permissions.

## NO_TRADE Behavior

`NO_TRADE` is a first-class engine. It has a contract with zero size, zero max loss, no entry mode, and no exit mode. It remains valid even when all other engines reject.

## HUNT Approval Boundary

HUNT cannot route without explicit `hunt_approval=true`. This is a conservative placeholder until V2.14 Risk Governor exists.

## Reproducibility

Every route stores:

- opportunity score and band
- candidate engine suggestions
- risk flags
- no-trade reasons
- engine decisions
- selected engine
- route status
- reproducibility hash

Identical inputs produce the same hash.

## Insufficient Data

Missing opportunity score, missing inputs, or insufficient V2.11 data produces `INSUFFICIENT_DATA` and selects `NO_TRADE`. Missing data is not guessed.

## Dashboard Fields

The dashboard overview includes DB-backed `strategy` truth:

- strategy_status
- runs_today
- routes_today
- no_trade_today
- blocked_today
- active_cooldowns
- latest_route_ts
- routes_by_engine
- rejections_by_engine
- top_route_reasons
- common_rejection_reasons
- recent_routes
- recent_no_trade_routes
- engine_confidence_average
- errors

No fake data is emitted.

## Safety Boundaries

- Strategy Router cannot create orders.
- Strategy Router cannot create order intents.
- Strategy Router cannot create exits.
- Strategy Router cannot mutate balances.
- Strategy Router cannot reserve capital.
- Engine contracts are not executable orders.
- State Governor is respected.
- HUNT requires explicit approval.
- Hard opportunity blocks force `NO_TRADE`/`BLOCKED`.
- Candidate engines are revalidated.

## Testing

Coverage includes engine rules, full contract fields, hard block routing, HUNT approval, candidate revalidation, REINVEST metadata-only behavior, API routes, persistence, event publication, and no trading side effects.

## Known Limitations

- V2.12 does not allocate capital.
- V2.12 does not approve risk.
- V2.12 does not execute or monitor exits.
- HUNT approval is an explicit input boundary until V2.14.
- REINVEST remains metadata-only until V2.13.

## Next Recommended Phase

V2.13 Capital Allocator V2 + Reinvest Brain.

