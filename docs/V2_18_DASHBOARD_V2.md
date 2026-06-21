# V2.18 Dashboard V2

## Purpose

V2.18 creates the operator-grade POLYBOT dashboard surface. It is a read-only cockpit for real DB/runtime truth across runtime state, event flow, neurons, memory, brains, opportunities, strategy, capital, risk, execution, exits, and no-trade intelligence.

The dashboard does not create trades, orders, order intents, exits, live requests, or balance mutations.

## Architecture

The repository has no React, Next, Vite, Tailwind, or `package.json` frontend stack. The actual frontend stack is the existing FastAPI-served dashboard HTML in `app/api/routes.py`.

V2.18 extends that stack:

- `DashboardV2QueryService` wraps existing DB-backed `OperatorDashboardQueryService` truth.
- `/dashboard/api/v2/*` endpoints return a consistent truth envelope.
- `/dashboard` serves a dark cockpit shell with navigation, status pills, stale banners, live-flow visual, and locked advanced-control panel.

No new dashboard DB tables are required.

## API Routes

Each route returns:

- `status`
- `updated_at`
- `stale`
- `stale_reason`
- `data_source`
- `data_confidence`
- `errors`
- `data`

Routes:

- `GET /dashboard/api/v2/overview`
- `GET /dashboard/api/v2/events`
- `GET /dashboard/api/v2/risk`
- `GET /dashboard/api/v2/engines`
- `GET /dashboard/api/v2/ai`
- `GET /dashboard/api/v2/no-trade`
- `GET /dashboard/api/v2/memory`
- `GET /dashboard/api/v2/market`
- `GET /dashboard/api/v2/opportunities`
- `GET /dashboard/api/v2/capital`
- `GET /dashboard/api/v2/execution`
- `GET /dashboard/api/v2/exits`
- `GET /dashboard/api/v2/news`
- `GET /dashboard/api/v2/social`
- `GET /dashboard/api/v2/whales`
- `GET /dashboard/api/v2/live-flow`
- `GET /dashboard/api/v2/settings`

## Pages

- Overview: mode, health, capital, PnL, risk, opportunities, kill state, AI cost, event bus, live certification.
- Live Flow: pipeline across data, neurons, memory, brains, opportunity, strategy, capital, risk, execution, exits, no-trade, events.
- Markets: data foundation, technical truth, ranking.
- Opportunities: V2.11 score and blocked truth.
- Engines: V2.12 routes, decisions, rejections, cooldowns.
- Risk: V2.14 governor, gate, breaches, cooldowns.
- Capital: V2.13 capital state, budgets, allocations, profit pocket, attack bank.
- Positions: V2.15 internal execution truth through orders/fills.
- Exits: V2.16 exit plans, intents, failures, quality, orphans.
- News, Social, Whales: neuron truth.
- AI Brain: AI request/cost/cache/model truth.
- Memory: market, no-trade, whale, and rules memory summaries.
- No-Trade: V2.17 reasons, regret, pending reviews, logs.
- Events: event bus and audit truth.
- Advanced Control: locked UI only; no write control API added.

## UI Design System

The UI is a premium dark cockpit:

- graphite/black base
- cyan/blue/violet accents
- green only for healthy states
- yellow for stale/warning states
- red for serious blocked/kill states
- sharp panels with subtle depth
- status pills and controlled pulse indicators only when data exists
- no decorative fake values

## Dashboard Truth Policy

All page data comes from:

- Postgres-backed query services
- runtime health/state services
- existing persisted phase tables

If data is absent, sparse, or stale, the response and UI show `NO_DATA`, `INSUFFICIENT_DATA`, `STALE`, or `DEGRADED`. The dashboard does not invent values.

## Stale Data Policy

The V2 envelope computes freshness from source timestamps where available. If no source timestamp exists, the page is marked stale with a reason. The default stale threshold is 20 minutes.

## Advanced Control Policy

V2.18 adds no new control/write API.

The Advanced Control page is locked and shows:

- unlock required
- actor required
- reason required
- confirmation required
- audit required
- no one-click dangerous control

If a user tries the visible action without a reason and confirmation, the UI blocks locally. If reason and confirmation are present, the UI still blocks because no safe Dashboard V2 control endpoint exists in this phase.

## Safety Boundaries

- Dashboard cannot create orders.
- Dashboard cannot create order intents.
- Dashboard cannot create live exits.
- Dashboard cannot mutate external balances.
- Dashboard cannot enable live trading.
- Dashboard does not bypass State Governor or Risk Governor.
- Live certification remains false.

## Tests

V2.18 tests cover:

- route registration
- required truth envelope
- DB-backed endpoint responses
- stale/no-data honesty
- locked advanced-control policy
- no mutation of order/execution/exit tables
- no unknown action execution

## Remaining Risks

- The UI remains a FastAPI-served HTML shell rather than a separate frontend application, because that is the actual repo stack.
- Some endpoint responses can be slow while the single-process runtime is refreshing markets; this is inherited from the current synchronous runtime.
- Advanced controls are intentionally non-operational until a future phase exposes audited safe backend control endpoints.

## Next Recommended Phase

V2.19 Feedback / Learning Loop.
