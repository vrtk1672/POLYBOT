# V2.15 Execution Cortex V2

## Purpose

V2.15 adds internal paper/shadow execution infrastructure. It represents, simulates, monitors, cancels, and quality-scores internal execution contracts from strategy routes, capital allocations, and Risk Gate approvals.

V2.15 is not live execution. It does not send external orders, create order intents, create exits, mutate external balances, or enable live trading.

## Architecture

- `app/execution_v2/contracts.py` defines order, precheck, fill, shadow, and quality contracts.
- `order_contract_builder.py` builds LIMIT-only internal contracts from orderbook truth.
- `paper_execution_simulator.py` simulates PAPER_SIM orders against depth and slippage.
- `shadow_execution_planner.py` creates SHADOW_PLAN records with `not_sent_reason`.
- `fill_simulator.py`, `partial_fill_handler.py`, and `failed_fill_handler.py` model fills without touching external systems.
- `cancel_condition_evaluator.py` evaluates internal cancel conditions.
- `execution_quality.py` records expected-vs-actual simulation quality.
- `service.py` coordinates prechecks, persistence, events, and read APIs.

## DB Tables

Migration: `app/db/migrations/0053_v2_15_execution_cortex_v2.sql`.

Tables:

- `orders_v2`: internal paper/shadow order contracts and lifecycle state.
- `order_events_v2`: order lifecycle audit trail.
- `fills_v2`: paper/shadow fill simulation records.
- `execution_errors`: execution-layer blocks and errors.
- `execution_latency`: execution timing records.
- `execution_quality`: fill/slippage/quality scoring.

`orders_v2.execution_mode` is constrained to `PAPER_SIM` and `SHADOW_PLAN`.

## API Routes

- `GET /execution/health`
- `GET /execution/orders/recent`
- `GET /execution/orders/{order_id}`
- `GET /execution/fills/recent`
- `GET /execution/errors/recent`
- `GET /execution/quality/recent`
- `POST /execution/precheck`
- `POST /execution/paper/simulate`
- `POST /execution/shadow/plan`
- `POST /execution/cancel-evaluate`

## Event Types

- `execution.order.created`
- `execution.order.blocked`
- `execution.order.submitted_paper`
- `execution.order.planned_shadow`
- `execution.order.partially_filled`
- `execution.order.filled`
- `execution.order.failed`
- `execution.order.cancelled`
- `execution.cancel_condition.triggered`
- `execution.fill.created`
- `execution.quality.recorded`
- `execution.error.recorded`
- `execution.live.blocked`

## Order Contract

V2.15 builds `LIMIT` contracts only. Price is derived from bid/ask/mid/depth, not last price alone. Contracts carry:

- strategy route reference
- capital allocation reference
- risk decision reference
- required `exit_plan_id`
- orderbook/liquidity/fee/risk snapshots
- max slippage and TTL
- cancel conditions

## Precheck Logic

Execution blocks unless all required inputs are present:

- non-`NO_TRADE` strategy route
- `ALLOCATED` or `REDUCED` capital allocation
- `APPROVED` or `REDUCED` Risk Gate decision
- governor state compatible with execution
- `exit_plan_id`
- bid/ask and depth
- acceptable slippage
- runtime mode compatible with requested execution mode

`DATA_ONLY` blocks persisted PAPER_SIM execution. `PAPER` allows PAPER_SIM only. `SHADOW_LIVE` allows SHADOW_PLAN only. `SMALL_LIVE` and `ATTACK_MODE` return `live_not_certified`.

## Paper Simulation

Paper simulation consumes orderbook depth and spread:

- full fill when depth supports size and slippage is acceptable
- partial fill when depth is insufficient but still usable
- failed fill for missing depth or excessive slippage
- fee, slippage, fill probability, and liquidity consumed are recorded

## Shadow Plan

Shadow planning persists a non-sent `SHADOW_PLAN` contract only. It records expected fill probability, expected slippage, latency estimate, cancel conditions, and `not_sent_reason=shadow_plan_only_no_external_send`.

## Cancel Conditions

Supported internal cancel triggers:

- `spread_widens`
- `score_drops`
- `news_reversal`
- `fill_rate_too_low`
- `depth_drops`
- `risk_governor_blocks`
- `ttl_expired`
- `slippage_too_high`

Triggered conditions update internal `orders_v2` state and write `order_events_v2`. They do not affect external systems.

## Execution Quality

`execution_quality` compares expected fill price/slippage/probability with simulated results, fill ratio, failed fills, partial fills, and cancellations.

## Live Certification Boundary

`live_certified=false` is hard-coded for V2.15. No live mode, live order sender, venue adapter, or external balance mutation exists in this phase.

## Insufficient Data Behavior

Missing route, allocation, risk approval, exit plan, bid/ask, or depth returns explicit block reasons. V2.15 prefers blocked/precheck output over invented execution assumptions.

## Dashboard Fields

The dashboard query service exposes real DB-backed `execution` overview:

- `execution_status`
- `live_certified`
- `orders_today`
- `paper_orders_today`
- `shadow_plans_today`
- `fills_today`
- `partial_fills_today`
- `failed_fills_today`
- `cancelled_today`
- `avg_slippage_bps`
- `avg_quality_score`
- `recent_orders`
- `recent_fills`
- `recent_errors`
- `recent_quality`
- `live_blocked_count`
- `errors`

## Safety Boundaries

- No live orders.
- No order intents.
- No exits.
- No external balance mutation.
- No external venue requests.
- No market orders.
- No execution without Risk Gate approval.
- No execution without `exit_plan_id`.
- Shadow execution sends nothing.

## Remaining Risks

- Real orderbook truth depends on available V2.8 orderbook/liquidity rows or explicit safe smoke payloads.
- V2.16 must create real exit plans; V2.15 only requires an `exit_plan_id` reference.
- Runtime startup via canonical PowerShell remains affected by Windows Application Control, so direct Python startup is the verified fallback.

## Next Recommended Phase

V2.16 Exit Cortex V2.

