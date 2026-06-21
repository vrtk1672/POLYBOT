# V2.13 Capital Allocator V2 + Reinvest Brain

## Purpose

V2.13 adds the internal money brain. It answers which capital bucket can fund a validated V2.12 strategy route, how much may be allocated, which reserves must remain untouched, and how realized profit can feed the Profit Pocket and Attack Bank.

It does not create orders, order intents, exits, risk approvals, live requests, or external balance mutations.

## Architecture

- `app/capital/contracts.py`: capital state, budgets, allocation request/decision, reinvest contracts.
- `app/capital/capital_state_builder.py`: builds internal capital truth from canonical paper DB state or explicit smoke input.
- `app/capital/engine_budget_manager.py`: derives engine budgets and bucket mappings.
- `app/capital/allocation_policy.py`: applies reserve, budget, route-status, loss-streak, and aggressive-engine caps.
- `app/capital/capital_allocator.py`: V2 allocator wrapper.
- `app/capital/reinvest_brain.py`: evaluates realized-profit-only reinvest movement.
- `app/capital/profit_pocket_manager.py`: profit pocket accounting helper.
- `app/capital/attack_bank_manager.py`: attack bank accounting helper with base capital locked out.
- `app/capital/loss_streak_policy.py`: allocation reduction policy after losses.
- `app/capital/service.py`: runtime guard, DB persistence, event publication, and read APIs.
- `app/api/capital_routes.py`: read endpoints plus safe rebuild/allocation/reinvest endpoints.

## DB Tables

Migration: `app/db/migrations/0051_v2_13_capital_allocator_reinvest_brain.sql`

- `capital_state_v2`: canonical internal capital snapshot.
- `engine_budgets`: per-engine and per-bucket policy budgets.
- `capital_allocations_v2`: allocation decisions for strategy routes. These are not orders.
- `reinvest_ledger`: reinvest and realized-profit movement audit.
- `profit_pocket`: realized profit pool.
- `attack_bank`: aggressive capital funded by realized profit only. `base_capital_used_usd` is constrained to `0`.
- `capital_events`: capital audit events.

## API Routes

- `GET /capital/health`
- `GET /capital/state`
- `GET /capital/budgets`
- `GET /capital/allocations/recent`
- `GET /capital/events/recent`
- `GET /capital/reinvest`
- `POST /capital/state/rebuild`
- `POST /capital/allocate`
- `POST /capital/reinvest/evaluate`

The POST endpoints are internal accounting endpoints only. They do not mutate broker/exchange balances or create execution artifacts.

## Events

- `capital.state.created`
- `capital.state.updated`
- `engine.budget.created`
- `engine.budget.updated`
- `capital.allocation.created`
- `capital.allocation.blocked`
- `capital.allocation.reduced`
- `reinvest.profit_pocket.updated`
- `reinvest.attack_bank.updated`
- `capital.event.recorded`
- `capital.insufficient_data`

## Bucket Policy

- SAFE -> `SAFE_CAPITAL`
- STRIKE -> `STRIKE_CAPITAL`
- CONVEX -> `CONVEX_CAPITAL`, or `ATTACK_BANK` when realized-profit attack capital exists.
- MAKER -> `MAKER_CAPITAL`
- HUNT -> `HUNT_CAPITAL`, or `ATTACK_BANK` when explicitly available.
- MOONSHOT_BASKET -> `MOONSHOT_BASKET`, with small basket sizing.
- REINVEST -> `PROFIT_POCKET` metadata and ledger support.
- NO_TRADE -> no allocation.

## Allocation Logic

V2.13 blocks or reduces allocation when:

- capital data is missing;
- strategy route is `NO_TRADE`, `BLOCKED`, or `INSUFFICIENT_DATA`;
- engine budget is missing, disabled, exhausted, or cooling down;
- survival reserve or cash reserve would be violated;
- loss streak policy reduces or blocks aggressive engines;
- HUNT, CONVEX, or MOONSHOT would consume too much capital.

The allocation record stores requested size, approved size, bucket, max loss, reserve-after value, projected engine budget after decision, reason, and constraints.

## Reinvest Logic

Realized profit can enter Profit Pocket. A configured portion can move into Attack Bank. In V2.13, Attack Bank cannot use base capital and does not perform real transfers.

If no realized profit exists, reinvest is blocked or no movement occurs.

## Dashboard Fields

The dashboard query service exposes a DB-backed `capital` overview:

- `capital_status`
- `total_capital`
- `available_capital`
- `locked_capital`
- `survival_reserve`
- `cash_reserve`
- `profit_pocket`
- `attack_bank`
- `allocations_today`
- `blocked_allocations_today`
- `reduced_allocations_today`
- `budgets_by_engine`
- `allocation_by_bucket`
- `recent_capital_events`
- `loss_streak_count`
- `reinvest_status`
- `insufficient_data_count`
- `errors`

No fake dashboard data is introduced.

## Safety Boundaries

- Capital Allocator cannot create orders.
- Capital Allocator cannot create order intents.
- Capital Allocator cannot create exits.
- Capital Allocator cannot mutate external balances.
- Allocation decisions are not executable orders.
- Reserves are preserved.
- Engine budgets are respected.
- Attack Bank is realized-profit-only.
- NO_TRADE/BLOCKED routes receive no allocation.
- Missing capital data is explicit.

## Known Limitations

- Real capital source maturity depends on existing paper/live balance infrastructure.
- V2.13 does not reserve funds or approve risk; that remains future V2.14+ work.
- Reinvest movement is internal accounting, not a broker transfer.

## Next Phase

V2.14 Risk Gate + Risk Governor can consume V2.13 allocation decisions after V2.13 is verified GREEN.

