# POLYBOT V3.5 Capital Brain Upstream

## Purpose

V3.5 moves Capital from a late paper execution guard into an upstream mesh brain participant.

The existing `PaperCapitalService` remains the canonical paper balance and ledger authority. V3.5 does not lock, release, allocate, or mutate capital. It creates derived session evaluations that future gates and coordinator phases can read before paper intent or execution.

## Current Reality

Paper Capital already exists as a paper-only bankroll layer:

- `paper_accounts` stores the default paper account.
- `paper_capital_ledger` records lock/release/PnL and guard events.
- `PaperExecutionService` calls `PaperCapitalService.precheck_fill()` before fill/position creation.
- `PaperCapitalService.lock_on_fill()` and `release_on_close()` are the balance mutation points.

V3.3 already had a `CAPITAL_BRAIN` opinion, but it only consumed Shared Awareness capital domain state. It did not have its own upstream evaluation record, constraints, source links, or dashboard surface.

V3.5 adds that missing upstream layer.

## Data Model

Migration `0106_v3_capital_brain_upstream.sql` creates:

- `capital_brain_evaluations`
- `capital_brain_sources`

`capital_brain_evaluations` stores one idempotent current evaluation per mesh session.

`capital_brain_sources` links each evaluation back to source rows such as:

- `mesh_shared_awareness`
- `paper_accounts`
- `paper_capital_ledger`
- `paper_positions` when applicable

## Decisions

Allowed decisions:

- `CAPITAL_SUPPORT`
- `CAPITAL_WATCH`
- `CAPITAL_BLOCK`
- `CAPITAL_RELEASE_REVIEW`
- `CAPITAL_INSUFFICIENT_DATA`

## Candidate And Market Rules

The deterministic evaluator blocks when:

- account state is missing
- available capital is zero
- estimated required capital exceeds available balance
- estimated required capital exceeds max position size
- daily loss guard is active
- max open positions is reached
- open exposure would exceed max exposure

It watches when:

- exposure is near the max limit
- expected capital lock is long and fees/edge are poor or missing
- liquidity is poor or stale
- capital efficiency is weak

It supports when:

- balance, exposure, limits, liquidity, and efficiency fit the session

Missing news, social, or whale evidence does not block by itself.

## Position Rules

For position sessions:

- profitable plus adverse risk/exit context -> `CAPITAL_RELEASE_REVIEW`
- adverse risk/exit context -> `CAPITAL_RELEASE_REVIEW`
- healthy position context -> `CAPITAL_WATCH`
- no position context -> `CAPITAL_INSUFFICIENT_DATA`

V3.5 recommends release review only. It does not release capital.

## Runtime Integration

The flow is now:

Neural event -> Mesh Session -> Shared Awareness -> Capital Brain Evaluation -> Multi-Brain Consumption -> Coordinator Input Bundle -> Mesh Coordinator Decision

Integration point:

- `SharedAwarenessService.refresh_session_with_conn()` evaluates capital before invoking `MultiBrainConsumptionService`.
- `MultiBrainConsumptionService` extends its existing `CAPITAL_BRAIN` opinion from `capital_brain_evaluations` when present.
- The mesh coordinator sees the capital result through the existing `mesh_brain_opinions` and bundle path.

System behavior:

- System OFF blocks runtime evaluation mutation.
- System ON allows source-backed derived evaluations.
- Dashboard reads remain allowed.

## Dashboard

Routes:

- `GET /dashboard/api/v2/capital-brain`
- `GET /dashboard/api/v2/capital-brain/{evaluation_id}`
- `GET /dashboard/api/v2/capital-brain/session/{session_id}`

All routes return `mock_data=false`.

## Dialogue

Brain Dialogue materializes source-backed Capital Brain messages from `capital_brain_evaluations`.

Example:

`Capital Brain: Available=1000.00000000, locked=0E-8, exposure=0E-8. I capital support session ... because Capital Brain supports upstream review; balance, exposure, and limits fit the session.`

## Safety

V3.5 does not mutate:

- `paper_accounts`
- `paper_capital_ledger`
- `live_orders`
- `paper_orders`
- `paper_fills`
- `paper_positions`
- `paper_intents`
- `orders_v2`
- `fills_v2`
- canonical `positions`
- `risk_decisions`
- `exit_plans`
- eligibility outcomes
- legacy `coordinator_decisions`
- `brain_outputs`

## Next Phase

Position-Aware Reactions, after required ChatGPT review.
